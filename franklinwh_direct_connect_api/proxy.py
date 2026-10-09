"""
Transparent decoding proxy for the FranklinWH local broker channel.

Sits between the FranklinWH mobile app (client) and a **real aGate**, forwards
every byte verbatim in both directions, and decodes each frame for logging —
so you can watch the live conversation in cleartext and, crucially, surface the
**unknown cmdTypes** (the write/control codes not yet in the catalog).

It is **passive**: frames are never modified, dropped, or reordered — bytes are
relayed first, then decoded for the log. Point the app at this proxy instead of
the aGate (via ARP-spoof + DNAT, a host route, or anything that redirects
``:9000``), and drive the app while watching the output.

    from franklinwh_direct_connect_api.proxy import serve, log_frame
    serve("0.0.0.0", 9000, "192.0.2.110", 9000, on_frame=log_frame)

A direction label is passed to ``on_frame``: ``"app->aGate"`` (requests, usually
the interesting writes) or ``"aGate->app"`` (replies).
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
import time
from typing import Callable

from . import catalog, protocol
from .protocol import Frame

FrameCallback = Callable[[str, Frame], None]

APP_TO_AGATE = "app->aGate"
AGATE_TO_APP = "aGate->app"


class PcapWriter:
    """Record the proxied TCP/9000 conversation to a classic pcap, on demand.

    Wraps the real payload bytes in synthetic Ethernet/IPv4/TCP framing (RFC 5737
    addresses), so the file opens in Wireshark and re-decodes with
    :func:`franklinwh_direct_connect_api.protocol.iter_pcap_frames`. It is a faithful record of
    the application-layer byte stream (which is all the decoder needs), not a
    wire-exact packet capture. Thread-safe: both relay directions write to it.
    """

    _CLIENT_IP = b"\xc0\x00\x02\x32"   # 192.0.2.50
    _AGATE_IP = b"\xc0\x00\x02\x0a"    # 192.0.2.10
    _CLIENT_PORT = 54321
    _AGATE_PORT = 9000                    # canonical local port (what the capture represents)

    def __init__(self, path: str):
        self._f = open(path, "wb")
        self._f.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))  # global hdr, Ethernet
        self._seq = {APP_TO_AGATE: 1, AGATE_TO_APP: 1}
        self._lock = threading.Lock()

    @staticmethod
    def _ip_checksum(hdr: bytes) -> int:
        total = sum(struct.unpack(">%dH" % (len(hdr) // 2), hdr))
        total = (total >> 16) + (total & 0xFFFF)
        total += total >> 16
        return (~total) & 0xFFFF

    def write(self, direction: str, payload: bytes) -> None:
        if not payload:
            return
        if direction == APP_TO_AGATE:
            src, sp, dst, dp = self._CLIENT_IP, self._CLIENT_PORT, self._AGATE_IP, self._AGATE_PORT
        else:
            src, sp, dst, dp = self._AGATE_IP, self._AGATE_PORT, self._CLIENT_IP, self._CLIENT_PORT
        with self._lock:
            seq = self._seq[direction]
            self._seq[direction] = seq + len(payload)
            tcp = struct.pack(">HHIIBBHHH", sp, dp, seq, 0, (5 << 4), 0x18, 65535, 0, 0) + payload
            ip_hdr = struct.pack(">BBHHHBBH", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0) + src + dst
            cks = self._ip_checksum(ip_hdr)
            ip = struct.pack(">BBHHHBBH", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, cks) + src + dst
            eth = b"\x02\x00\x00\x00\x00\x02\x02\x00\x00\x00\x00\x01\x08\x00"
            pkt = eth + ip + tcp
            t = time.time()
            self._f.write(struct.pack("<IIII", int(t), int((t % 1) * 1_000_000), len(pkt), len(pkt)))
            self._f.write(pkt)
            self._f.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._f.close()
            except OSError:
                pass


def log_frame(direction: str, frame: Frame, *, file=sys.stdout) -> None:
    """Default ``on_frame``: one line per frame, flagging unknown cmdTypes."""
    known = frame.cmd_type in catalog.CATALOG or any(
        frame.cmd_type == i.response for i in catalog.CATALOG.values()
    )
    flag = "" if known else "  <-- UNKNOWN cmdType (candidate write/control code)"
    import json
    da = json.dumps(frame.data_area, separators=(",", ":"))
    if len(da) > 200:
        da = da[:200] + "…"
    print(f"{direction}  {frame.cmd_type} {frame.name}  snno={frame.snno}{flag}",
          file=file)
    print(f"    {da}", file=file, flush=True)


def _pump(src: socket.socket, dst: socket.socket, direction: str,
          on_frame: FrameCallback, on_bytes=None) -> None:
    """Relay src→dst verbatim, decoding frames out of the same byte stream."""
    stream = protocol.FrameStream()
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)  # forward first — the proxy must not add latency
            if on_bytes is not None:
                on_bytes(direction, chunk)   # record verbatim (never blocks the relay path meaningfully)
            try:
                for fr in stream.feed(chunk):
                    on_frame(direction, fr)
            except Exception as exc:  # a decode hiccup must never break the relay
                print(f"{direction}  [decode error: {exc}]", file=sys.stderr)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket, target: tuple[str, int],
            on_frame: FrameCallback, timeout: float, on_bytes=None) -> None:
    try:
        upstream = socket.create_connection(target, timeout)
    except OSError as exc:
        print(f"proxy: upstream connect to {target[0]}:{target[1]} failed: {exc}",
              file=sys.stderr)
        client.close()
        return
    t1 = threading.Thread(target=_pump, args=(client, upstream, APP_TO_AGATE, on_frame, on_bytes),
                          daemon=True)
    t2 = threading.Thread(target=_pump, args=(upstream, client, AGATE_TO_APP, on_frame, on_bytes),
                          daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    client.close()
    upstream.close()


def serve(
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
    *,
    on_frame: FrameCallback = log_frame,
    once: bool = False,
    timeout: float = 10.0,
    on_listen: Callable[[int], None] | None = None,
    record: str | None = None,
) -> None:
    """Relay between a client on ``listen_*`` and the aGate on ``target_*``.

    Blocks serving connections until interrupted. With ``once=True`` it serves a
    single connection and returns (used by the tests). ``listen_port=0`` binds an
    ephemeral port; ``on_listen`` is called with the actual bound port. Pass
    ``record=<path>`` to also write a pcap of the whole conversation (openable in
    Wireshark and re-decodable with ``iter_pcap_frames``).
    """
    writer = PcapWriter(record) if record else None
    on_bytes = writer.write if writer else None
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((listen_host, listen_port))
    srv.listen(5)
    bound_port = srv.getsockname()[1]
    if on_listen is not None:
        on_listen(bound_port)
    print(f"proxy: listening on {listen_host}:{bound_port} -> "
          f"{target_host}:{target_port}", file=sys.stderr)
    try:
        while True:
            client, addr = srv.accept()
            print(f"proxy: client {addr[0]}:{addr[1]} connected", file=sys.stderr)
            if once:
                _handle(client, (target_host, target_port), on_frame, timeout, on_bytes)
                return
            threading.Thread(
                target=_handle,
                args=(client, (target_host, target_port), on_frame, timeout, on_bytes),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\nproxy: stopped", file=sys.stderr)
    finally:
        srv.close()
        if writer is not None:
            writer.close()
