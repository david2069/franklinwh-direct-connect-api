"""
TCP transport for the FranklinWH aGate local broker protocol.

This connects to a host speaking the TCP/9000 frame protocol, performs the
login handshake, and exchanges request/response frames.

Connecting (Direct / hotspot mode)
----------------------------------
The aGate listens on TCP/9000 on its **own WiFi hotspot** (the "Direct
Connection" AP it broadcasts, e.g. SSID ``AP_<serial-suffix>``). The FranklinWH
mobile app joins that hotspot and connects to the gateway's AP-side address
(``10.100.1.1`` in captured traffic) on port 9000.

``DirectConnectTransport`` plays the **mobile-app client** role: join the FranklinWH
hotspot, then point it at the hotspot gateway IP. (In the capture the client
``10.100.1.81`` is the phone and ``10.100.1.1:9000`` is the aGate.)
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any

from . import protocol
from .protocol import Frame

_log = logging.getLogger(__name__)

DEFAULT_PORT = 9000
DEFAULT_TIMEOUT = 20.0   # seconds; generous for slow/flaky local wifi
DEFAULT_RETRIES = 2      # transient reconnect-retries per connect/request
ERROR_CMD = 9999         # aGate's generic error/unsupported-cmdType response frame
LOGIN_EQUIP = "00000000"
LOGIN_DATA_AREA = {"opt": 0, "minProtocolVer": "V1.00.00"}


class TransportError(RuntimeError):
    pass


class DirectConnectTransport:
    """
    Synchronous framed TCP client.

    Example
    -------
    >>> with DirectConnectTransport("10.100.1.1") as t:
    ...     manifest = t.login()                       # 1101 -> 1102
    ...     equip = manifest.data_area["IBG_SN"]
    ...     flow = t.request(1301, equip, {"opt": 0})  # -> 1302
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT, *,
                 timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
                 retry_backoff: float = 0.5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff = retry_backoff
        self._sock: socket.socket | None = None
        self._stream = protocol.FrameStream()
        self._pending: list[Frame] = []
        self._snno = 0
        self.equip_no: str | None = None
        self._logged_in = False   # re-login after a transient reconnect
        self._login_data_area: Any | None = None

    # -- connection lifecycle ------------------------------------------------
    def connect(self) -> None:
        if self._sock is not None:
            return
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self._sock = socket.create_connection((self.host, self.port), self.timeout)
                self._sock.settimeout(self.timeout)
                return
            except OSError as e:
                last = e
                if attempt < self.retries:
                    _log.warning("connect to %s:%s failed (%s); retry %d/%d",
                                 self.host, self.port, e, attempt + 1, self.retries)
                    time.sleep(self.retry_backoff * (attempt + 1))
        raise TransportError(
            f"could not connect to {self.host}:{self.port} after "
            f"{self.retries + 1} attempt(s): {last}"
        ) from last

    def _reconnect(self) -> None:
        """Drop the socket, reset framing state, reconnect (+ re-login if needed)."""
        self.close()
        self._stream = protocol.FrameStream()
        self._pending = []
        self.connect()
        if self._logged_in:
            self._do_login()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "DirectConnectTransport":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- framing -------------------------------------------------------------
    def _next_snno(self) -> int:
        self._snno += 1
        return self._snno

    def send_frame(
        self,
        cmd_type: int,
        equip_no: str,
        data_area: Any,
        *,
        time_stamp: int | None = None,
        snno: int | None = None,
        seed: int | None = None,
    ) -> int:
        """Encode and send a frame. Returns the snno used."""
        if self._sock is None:
            raise TransportError("not connected")
        s = self._next_snno() if snno is None else snno
        ts = int(time.time()) if time_stamp is None else time_stamp
        wire = protocol.encode_frame(
            cmd_type, equip_no, data_area, time_stamp=ts, snno=s, seed=seed
        )
        self._sock.sendall(wire)
        return s

    @staticmethod
    def _matches(fr: Frame, want_cmd: int | None) -> bool:
        """A frame satisfies a wait if it is the wanted response, any frame (when
        ``want_cmd`` is None), or the aGate's generic ``9999`` error response (which
        terminates the wait for an unsupported/rejected cmdType)."""
        return want_cmd is None or fr.cmd_type == want_cmd or fr.cmd_type == ERROR_CMD

    def recv_frame(self, *, want_cmd: int | None = None) -> Frame:
        """
        Read the next frame (optionally the next matching ``want_cmd``).
        Buffers any non-matching frames for later reads.
        """
        if self._sock is None:
            raise TransportError("not connected")
        # serve from buffer first
        for i, fr in enumerate(self._pending):
            if self._matches(fr, want_cmd):
                return self._pending.pop(i)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            chunk = self._sock.recv(8192)
            if not chunk:
                raise TransportError("connection closed by peer")
            for fr in self._stream.feed(chunk):
                if self._matches(fr, want_cmd):
                    return fr
                self._pending.append(fr)
        raise TimeoutError(f"no frame{f' {want_cmd}' if want_cmd else ''} within {self.timeout}s")

    # -- request/response ----------------------------------------------------
    #: The most recent ``{"cmdType", "dataArea"}`` actually put on the wire.
    last_request: dict | None = None

    def request(self, cmd_type: int, equip_no: str, data_area: Any | None = None) -> Frame:
        """Send a request and return its paired response frame.

        On a transient failure (timeout, connection reset) the transport
        reconnects (re-logging in if a login was performed) and retries, up to
        ``self.retries`` times. aGate requests here are idempotent set-to-value
        operations, so a retry cannot double-apply a change.
        """
        # Record the frame we are about to send, so callers can SHOW what was sent
        # rather than asking anyone to trust a reconstruction. Overwritten per call.
        self.last_request = {"cmdType": int(cmd_type), "dataArea": data_area}

        from . import catalog
        if data_area is None:
            data_area = {"opt": 0}
        want = catalog.response_for(cmd_type)
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if self._sock is None:
                    self._reconnect()
                self.send_frame(cmd_type, equip_no, data_area)
                return self.recv_frame(want_cmd=want)
            except (TransportError, TimeoutError, OSError) as e:
                last = e
                if attempt < self.retries:
                    _log.warning("request %s failed (%s); reconnecting (attempt %d/%d)",
                                 cmd_type, e, attempt + 1, self.retries)
                    try:
                        self._reconnect()
                    except (TransportError, TimeoutError, OSError) as re:
                        last = re
                    time.sleep(self.retry_backoff * (attempt + 1))
        raise last if last is not None else TransportError("request failed")

    def login(self, *, data_area: Any | None = None) -> Frame:
        """
        Perform the 1101 handshake and return the 1102 manifest frame.
        Also records ``equip_no`` (IBG_SN) for subsequent requests, and marks the
        session so a transient reconnect re-logs-in automatically.

        Retries the handshake on transient failures (login is the entry point for
        every command, so it must be as resilient as ``request``).
        """
        self._login_data_area = data_area
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if self._sock is None:
                    self.connect()
                resp = self._do_login()
                self._logged_in = True
                return resp
            except (TransportError, TimeoutError, OSError) as e:
                last = e
                if attempt < self.retries:
                    _log.warning("login failed (%s); reconnecting (attempt %d/%d)",
                                 e, attempt + 1, self.retries)
                    self.close()
                    self._stream = protocol.FrameStream()
                    self._pending = []
                    time.sleep(self.retry_backoff * (attempt + 1))
        raise last if last is not None else TransportError("login failed")

    def _do_login(self) -> Frame:
        self.send_frame(
            1101, LOGIN_EQUIP,
            LOGIN_DATA_AREA if self._login_data_area is None else self._login_data_area,
            seed=protocol.SEED_LOGIN,
        )
        resp = self.recv_frame(want_cmd=1102)
        if isinstance(resp.data_area, dict):
            self.equip_no = resp.data_area.get("IBG_SN") or resp.equip_no
        return resp


#: Pre-0.4.0 name. Same object; removal in 0.5.0.
LocalTransport = DirectConnectTransport
