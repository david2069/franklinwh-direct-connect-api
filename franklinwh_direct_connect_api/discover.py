"""
LAN discovery for FranklinWH gateways.

Scans hosts for the two ports that matter for local access:

* **TCP 9000** — the aGate ``sendMqtt`` Direct-Connection listener. The aGate
  exposes this on its **own WiFi hotspot** (SSID ``AP_<serial-suffix>``); join
  that hotspot first, then the gateway is the hotspot gateway IP (typically the
  ``.1`` of the hotspot subnet, e.g. ``10.100.1.1``).
* **TCP 502** — Modbus TCP, which the aGate's LocRemCtl path uses for local
  control when available.

Tip: when joined to the FranklinWH hotspot, scanning the hotspot gateway (or its
/24) is usually enough — see ``default_gateway()``.

Open-port detection is a plain non-blocking connect. Two optional probes go
further and *confirm* the service:

* ``probe_sendmqtt`` opens a connection, performs the 1101 login, and checks for
  a 1102 manifest reply.
* ``probe_modbus`` sends a Modbus "read holding registers" request and checks
  for a valid MBAP response (including exception responses).

Standard library only. Use responsibly and only on networks you own.
"""

from __future__ import annotations

import ipaddress
import socket
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable

from . import protocol

PORT_SENDMQTT = 9000
PORT_MODBUS = 502


# ---------------------------------------------------------------------------
# Target expansion
# ---------------------------------------------------------------------------
def expand_targets(spec: str) -> list[str]:
    """
    Expand a target spec into host strings.

    Accepts a single host/IP, a CIDR (``10.0.0.0/24``), a hyphen range
    (``10.0.0.1-10.0.0.50``), or a comma-separated mix of the above.

    Raises ``ValueError`` for tokens that look like bare integers (e.g. ``502``
    instead of an IP address) to catch common confusion between ports and hosts.
    """
    hosts: list[str] = []
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        if "/" in part:
            try:
                net = ipaddress.ip_network(part, strict=False)
            except ValueError:
                raise ValueError(
                    f"invalid CIDR {part!r} — expected e.g. 192.0.2.0/24"
                ) from None
            hosts.extend(str(h) for h in net.hosts())
        elif "-" in part and part.count(".") >= 3:
            lo, hi = part.split("-", 1)
            try:
                a, b = int(ipaddress.ip_address(lo)), int(ipaddress.ip_address(hi))
            except ValueError:
                raise ValueError(
                    f"invalid range {part!r} — expected e.g. 192.0.2.1-192.0.2.50"
                ) from None
            hosts.extend(str(ipaddress.ip_address(i)) for i in range(a, b + 1))
        else:
            # Bare token: validate it looks like an IP/hostname, not a port number.
            # A token that is purely digits (e.g. '502') is almost certainly a
            # port number passed in the wrong position — reject it clearly.
            if part.isdigit():
                raise ValueError(
                    f"{part!r} looks like a port number, not a host. "
                    f"Did you mean to pass a host or CIDR? "
                    f"(e.g. 'gateway', '192.0.2.0/24', '10.100.1.1')"
                )
            hosts.append(part)
    return hosts


# ---------------------------------------------------------------------------
# Low-level checks
# ---------------------------------------------------------------------------
def expand_ports(spec: str) -> list[int]:
    """
    Expand a port spec into port numbers.

    Accepts a single port (``9000``), a hyphen range (``9020-9030``), or a
    comma-separated mix (``9000,9020-9030``). Duplicates are removed and the
    result is sorted, so ``"9000,9000,9002-9001"`` is an error rather than a
    surprise.

    The companion to :func:`expand_targets`, and separate from it for the same
    reason that function rejects a bare integer: a port where a host belongs is
    the easy mistake, and it should fail loudly rather than scan nothing.

    Raises ``ValueError`` for a port outside 1-65535, a reversed range, or a
    token that is not a number.
    """
    ports: list[int] = []

    def _one(tok: str) -> int:
        try:
            n = int(tok)
        except ValueError:
            raise ValueError(
                f"invalid port {tok!r} — expected a number, e.g. 9000"
            ) from None
        if not 1 <= n <= 65535:
            raise ValueError(f"port {n} out of range — expected 1-65535")
        return n

    for part in (p.strip() for p in spec.split(",") if p.strip()):
        if "-" in part.lstrip("-"):
            lo_s, hi_s = part.split("-", 1)
            lo, hi = _one(lo_s.strip()), _one(hi_s.strip())
            if hi < lo:
                raise ValueError(
                    f"reversed port range {part!r} — expected low-high, e.g. 9020-9030"
                )
            ports.extend(range(lo, hi + 1))
        else:
            ports.append(_one(part))
    return sorted(set(ports))


def default_gateway() -> str | None:
    """
    Best-effort guess of the current default-gateway IP (the hotspot gateway,
    when joined to the FranklinWH AP). Uses a UDP socket trick — no traffic is
    actually sent. Returns the local /24's ``.1`` as a heuristic.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.100.1.1", 9000))  # FranklinWH hotspot gateway (no packets sent)
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        net = ipaddress.ip_network(local_ip + "/24", strict=False)
        return str(next(net.hosts()))  # the .1 of the local subnet
    except OSError:
        return None


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def ping(host: str, timeout: float = 1.0) -> bool | None:
    """Cheap L3 reachability check via one ICMP echo (system ``ping``).

    Returns True if the host answers, False if it does not, or ``None`` if ping is
    unavailable/unusable (caller should then fall back to a TCP check). Use this FIRST:
    if the host is not even routable there is no point doing TCP connects with retries.
    """
    import subprocess
    try:
        # -c 1 = one echo; overall runtime is bounded by the subprocess timeout so we
        # avoid -t/-W (their meaning differs between macOS and Linux ping).
        proc = subprocess.run(
            ["ping", "-c", "1", host],
            capture_output=True, timeout=timeout + 1.0,
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except (FileNotFoundError, OSError):
        return None


def probe_modbus(host: str, port: int = PORT_MODBUS, timeout: float = 1.0) -> bool:
    """Send a minimal Modbus read and verify a valid MBAP response."""
    # MBAP: txn=1, proto=0, len=6, unit=1 ; PDU: fn=0x03 read holding, addr=0, qty=1
    req = struct.pack(">HHHB", 1, 0, 6, 1) + struct.pack(">BHH", 0x03, 0, 1)
    try:
        with socket.create_connection((host, port), timeout) as s:
            s.settimeout(timeout)
            s.sendall(req)
            hdr = s.recv(8)
            if len(hdr) < 8:
                return False
            # MBAP header is 7 bytes (txn, proto, len, unit); the 8th is the
            # function code. Unpack the 7-byte header only — feeding 8 bytes to
            # the 7-byte ">HHHB" format raises struct.error.
            txn, proto, _length, _unit = struct.unpack(">HHHB", hdr[:7])
            # Valid Modbus: protocol id 0, txn echoed; accept normal or exception fn.
            return proto == 0 and txn == 1
    except (OSError, struct.error):
        return False


def probe_sendmqtt(host: str, port: int = PORT_SENDMQTT, timeout: float = 2.0) -> dict | None:
    """
    Confirm a sendMqtt broker by performing the 1101 login and reading 1102.
    Returns the manifest dataArea on success, else None.
    """
    login = protocol.encode_frame(
        1101, "00000000", {"opt": 0, "minProtocolVer": "V1.00.00"},
        seed=protocol.SEED_LOGIN,
    )
    try:
        with socket.create_connection((host, port), timeout) as s:
            s.settimeout(timeout)
            s.sendall(login)
            stream = protocol.FrameStream()
            chunk = s.recv(8192)
            if not chunk:
                return None
            for fr in stream.feed(chunk):
                if fr.cmd_type == 1102 and isinstance(fr.data_area, dict):
                    return fr.data_area
    except (OSError, ValueError):
        return None
    return None


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
@dataclass
class HostResult:
    host: str
    sendmqtt_open: bool = False
    modbus_open: bool = False
    sendmqtt_confirmed: bool = False
    modbus_confirmed: bool = False
    manifest: dict | None = None

    @property
    def is_candidate(self) -> bool:
        return self.sendmqtt_open or self.modbus_open

    def summary(self) -> str:
        bits = []
        if self.sendmqtt_open:
            tag = "9000/sendMqtt"
            if self.sendmqtt_confirmed:
                sn = (self.manifest or {}).get("IBG_SN", "?")
                tag += f" CONFIRMED (IBG_SN={sn})"
            bits.append(tag)
        if self.modbus_open:
            bits.append("502/modbus" + (" CONFIRMED" if self.modbus_confirmed else ""))
        return f"{self.host}: " + (", ".join(bits) if bits else "no FranklinWH ports")


@dataclass
class PortResult:
    """One scanned ``(host, port)`` pair — the port is part of the identity.

    :class:`HostResult` carries booleans keyed by host and can only ever describe
    the two default ports, so it cannot represent two Direct Connect listeners on
    one address (an emulator host serving 9020-9024 collapses to a single row with
    the port recorded nowhere). This type exists for that case and is additive:
    ``scan`` and ``HostResult`` are unchanged.
    """

    host: str
    port: int
    open: bool = False
    confirmed: bool = False          # answered a real 1101 login handshake
    manifest: dict | None = None     # the 1102 reply, when confirmed

    @property
    def serial(self) -> str | None:
        """``IBG_SN`` from the login reply, or None if not confirmed."""
        return (self.manifest or {}).get("IBG_SN")

    def summary(self) -> str:
        if not self.open:
            return f"{self.host}:{self.port} closed"
        if not self.confirmed:
            return f"{self.host}:{self.port} open (no login reply — not a gateway)"
        return f"{self.host}:{self.port} CONFIRMED (IBG_SN={self.serial})"

    def __str__(self) -> str:
        return self.summary()


def scan_ports(
    targets: Iterable[str],
    ports: Iterable[int] = (PORT_SENDMQTT,),
    *,
    timeout: float = 0.5,
    workers: int = 128,
    probe: bool = True,
) -> list[PortResult]:
    """Scan every ``(host, port)`` pair for a Direct Connect listener.

    Unlike :func:`scan`, ``ports`` here is **the list of ports to scan**, not a
    filter over two constants — so a gateway or emulator on any port is found.
    Returns one :class:`PortResult` per open port, so two listeners on one host
    are two rows.

    ``probe=True`` confirms each open port with a real ``1101`` login handshake,
    which is what distinguishes a gateway from anything else listening. Modbus is
    not probed here: use :func:`scan` for that, unchanged.

    Raises ``KeyboardInterrupt`` (after cancelling in-flight threads) so a caller
    can print a clean exit message.
    """
    pairs = [(h, int(p)) for h in targets for p in ports]
    if not pairs:
        return []
    results: list[PortResult] = []

    def check(host: str, port: int) -> PortResult:
        r = PortResult(host, port)
        r.open = port_open(host, port, timeout)
        if probe and r.open:
            r.manifest = probe_sendmqtt(host, port, max(timeout, 2.0))
            r.confirmed = r.manifest is not None
        return r

    ex = ThreadPoolExecutor(max_workers=min(workers, max(1, len(pairs))))
    try:
        futs = {ex.submit(check, h, p): (h, p) for h, p in pairs}
        for fut in as_completed(futs):
            r = fut.result()
            if r.open:
                results.append(r)
    except KeyboardInterrupt:
        for f in futs:
            f.cancel()
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        ex.shutdown(wait=False)
    results.sort(key=lambda r: (r.host, r.port))
    return results


def scan(
    targets: Iterable[str],
    *,
    ports: tuple[int, ...] = (PORT_SENDMQTT, PORT_MODBUS),
    timeout: float = 0.5,
    workers: int = 128,
    probe: bool = True,
) -> list[HostResult]:
    """Scan targets; return one HostResult per host with an open target port.

    Raises ``KeyboardInterrupt`` (after cancelling in-flight threads) if the
    user hits Ctrl-C so the caller can print a clean exit message.
    """
    hosts = list(targets)
    results: dict[str, HostResult] = {}

    def check(host: str) -> HostResult:
        r = HostResult(host)
        if PORT_SENDMQTT in ports:
            r.sendmqtt_open = port_open(host, PORT_SENDMQTT, timeout)
        if PORT_MODBUS in ports:
            r.modbus_open = port_open(host, PORT_MODBUS, timeout)
        if probe and r.sendmqtt_open:
            r.manifest = probe_sendmqtt(host, PORT_SENDMQTT, max(timeout, 2.0))
            r.sendmqtt_confirmed = r.manifest is not None
        if probe and r.modbus_open:
            r.modbus_confirmed = probe_modbus(host, PORT_MODBUS, max(timeout, 1.0))
        return r

    ex = ThreadPoolExecutor(max_workers=min(workers, max(1, len(hosts))))
    try:
        futs = {ex.submit(check, h): h for h in hosts}
        for fut in as_completed(futs):
            r = fut.result()
            if r.is_candidate:
                results[r.host] = r
    except KeyboardInterrupt:
        # Cancel queued (not yet started) futures and do not wait for running
        # threads to finish — they are short-lived socket connects and will
        # complete within one timeout interval on their own.
        ex.shutdown(wait=False, cancel_futures=True)
        raise  # re-raise so _cmd_scan can print a clean interrupted message
    else:
        ex.shutdown(wait=True)

    return [results[h] for h in hosts if h in results]
