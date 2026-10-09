"""
Emulator / fake broker for the FranklinWH aGate local protocol.

Listens on a TCP port and answers request frames with canned responses, so the
client, CLI, scanner, and your own code can be exercised without real hardware.

Responses are synthesised by a deterministic per-seed :class:`SyntheticSite`, so no
capture is bundled or required. A caller may still pass ``pcap=<path>`` to replay their
own capture instead.

Run it::

    franklinwh-local emulate --port 9000
    # then, in another shell:
    franklinwh-local --host 127.0.0.1 power_flow
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

from . import catalog, protocol
from .protocol import Frame
from .synthetic import SyntheticSite

DEFAULT_EQUIP = "FAKEGATE90FJ09J6H4F2"

# Minimal fallback responses if no capture is available.
_FALLBACK: dict[int, dict[str, Any]] = {
    1102: {"opt": 0, "result": 0, "IBG_SN": DEFAULT_EQUIP, "protocolVer": "V1.11.01",
           "FHP_NUM": 1, "FHP_SN": ["FAKEAPOWERP6KMFY7ALA"]},
    1302: {"opt": 0, "result": 0, "mode": 85232, "name": "Self-Consumption",
           "p_uti": 19, "p_sun": -9, "p_gen": 0, "p_fhp": 509, "p_load": 519,
           "soc": 66.5, "t_amb": 22.9},
    1410: {"opt": 0, "result": 0, "SwMerge": 0, "Sw1Name": "Circuit 1", "Sw1Mode": 1},
    1202: {"opt": 0, "result": 0, "time": "2025-03-24 01:15:51", "timezone": 10,
           "postcode": "2069"},
}


def _load_canned(pcap: str | None) -> dict[int, str]:
    """Map response cmdType -> exact dataArea JSON string, from a capture."""
    canned: dict[int, str] = {}
    if pcap and Path(pcap).exists():
        try:
            for fr in protocol.iter_pcap_frames(pcap):
                # Never serve the captured login (1102) — it carries the real IBG_SN/FHP_SN
                # from the reference capture. The mock reports its own (fake) serials via
                # _FALLBACK / the synthetic manifest instead.
                if fr.cmd_type == 1102:
                    continue
                if not fr.is_request and fr.cmd_type not in canned and fr.data_area_raw:
                    canned[fr.cmd_type] = fr.data_area_raw
        except Exception:
            pass
    return canned



class Emulator:
    """A threaded fake broker. Use as a context manager or call serve_forever()."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000, *,
                 equip_no: str = DEFAULT_EQUIP, pcap: str | None = None,
                 seed: int | None = None, serial: str | None = None,
                 dynamic: bool = True, units: int = 1,
                 extra: dict[int, Any] | None = None):
        self.host = host
        self.port = port
        self.equip_no = equip_no
        self.units = max(1, int(units))
        self.canned = _load_canned(pcap)   # {} unless the caller supplies their own capture
        # A dynamic (per-seed) synthetic site drives the live-read cmdTypes at request
        # time. Build it when a seed is given, or when dynamic is on and there is no pcap
        # to answer from. ``--static`` (dynamic=False, no seed) keeps the canned/pcap path.
        self.site: SyntheticSite | None = None
        if dynamic and (seed is not None or not self.canned):
            self.site = SyntheticSite(seed or 0, serial)
            self.equip_no = self.site.serial
        elif serial is not None:
            self.equip_no = serial
        # Request-cmdType -> callable(request dataArea) -> reply dataArea | None.
        # Returning None sends no reply at all, which is how a real aGate behaves
        # for a cmdType it does not implement (or for the wrong payload shape).
        # Used to exercise payload-sensitive reads; see franklinwh_direct_connect_api.probe.
        self.extra = dict(extra or {})
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- response construction ----------------------------------------------
    def _dynamic_data(self, resp_cmd: int, req: dict | None = None) -> Any | None:
        """Payload built live from the synthetic site, or None to fall through.

        ``req`` is the request dataArea — the per-device reads take their aPower
        ``id`` from it so a multi-aPower emulator answers each unit distinctly.
        """
        site = self.site
        if site is None:
            return None
        now = time.time()
        dev_id = 1
        if isinstance(req, dict) and isinstance(req.get("id"), int):
            dev_id = req["id"]
        if resp_cmd == 1302:
            return site.snapshot(now)
        if resp_cmd == 1726:
            return site.mode_list(now)
        if resp_cmd == 1102:
            return site.login_manifest()
        if resp_cmd == 1404:
            return site.mode_config(now)
        if resp_cmd == 1708:
            return site.ibg_run_status(now)
        # -- multi-aPower battery reads --
        if resp_cmd in (1106, 1832):        # device_check / battery_modules
            return site.device_check(self.units)
        if resp_cmd == 1706:                # per-cell telemetry
            return site.battery_cells(dev_id, now)
        if resp_cmd == 1704:                # inverter & DC-bus
            return site.power_electronics(dev_id, now)
        if resp_cmd == 1836:               # states
            return site.device_states(dev_id, now)
        if resp_cmd == 1834:               # firmware
            return site.device_firmware(dev_id)
        # -- energy history / smart circuits / mode-set (incl. write round-trip) --
        if resp_cmd == 1304:                # 1303 daily energy history (needs date)
            return site.energy_history(req.get("date"), now)
        if resp_cmd == 1410:                # 1409 smart circuits: read, or persist a write
            if req.get("opt") == 1:
                return site.apply_smart_circuit_write(req)
            return site.smart_circuits()
        if resp_cmd == 1728:                # 1727 opt:3 set-mode -> persist
            return site.set_mode_write(req)
        return None

    def _reply_to(self, fr: Frame) -> bytes | None:
        handler = self.extra.get(fr.cmd_type)
        if handler is not None:
            reply = handler(dict(fr.data_area or {}))
            if reply is None:
                return None
            return protocol.encode_frame(fr.cmd_type + 1, self.equip_no, reply,
                                         snno=fr.snno)
        resp_cmd = catalog.response_for(fr.cmd_type)
        if resp_cmd is None:
            return None
        dyn = self._dynamic_data(resp_cmd, dict(fr.data_area or {}))
        if dyn is not None:
            data: Any = dyn
        else:
            raw = self.canned.get(resp_cmd)
            if raw is not None:
                data = raw  # exact captured dataArea string
            elif resp_cmd in _FALLBACK:
                data = _FALLBACK[resp_cmd]
            else:
                data = {"opt": 0, "result": 0}
        return protocol.encode_frame(resp_cmd, self.equip_no, data, snno=fr.snno)

    # -- serving -------------------------------------------------------------
    def _handle(self, conn: socket.socket) -> None:
        stream = protocol.FrameStream()
        with conn:
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(8192)
                except OSError:
                    return
                if not chunk:
                    return
                for fr in stream.feed(chunk):
                    reply = self._reply_to(fr)
                    if reply:
                        try:
                            conn.sendall(reply)
                        except OSError:
                            return

    def start(self) -> "Emulator":
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        return self

    def _accept_loop(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def serve_forever(self) -> None:
        self.start()
        try:
            while True:
                self._stop.wait(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def __enter__(self) -> "Emulator":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def run(host: str = "127.0.0.1", port: int = 9000, equip_no: str = DEFAULT_EQUIP, *,
        seed: int | None = None, serial: str | None = None, dynamic: bool = True,
        units: int = 1) -> int:
    emu = Emulator(host, port, equip_no=equip_no, seed=seed, serial=serial,
                   dynamic=dynamic, units=units)
    # flush=True so the "listening" line appears immediately in container logs
    # (Python block-buffers stdout when it is a pipe rather than a TTY).
    if emu.site is not None:
        print(f"FranklinWH emulator listening on {host}:{emu.port} "
              f"(dynamic seed={seed if seed is not None else 0} serial={emu.equip_no})",
              flush=True)
        print(f"  live cmdTypes 1302/1726/1102/1404/1708 generated per-request; "
              f"other reads canned ({len(emu.canned)} captured)", flush=True)
    else:
        print(f"FranklinWH emulator listening on {host}:{emu.port} "
              f"(static equipNo {emu.equip_no})", flush=True)
        print(f"  canned responses for cmdTypes: {sorted(emu.canned) or 'fallback only'}",
              flush=True)
    emu.serve_forever()
    return 0
