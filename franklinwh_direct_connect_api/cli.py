"""
Command-line interface for franklinwh-direct-connect.

Examples
--------
Decode a capture file (offline, no hardware needed)::

    franklinwh-direct-connect decode capture.pcap
    franklinwh-direct-connect decode capture.pcap --json

List the known command catalog::

    franklinwh-direct-connect catalog

Talk to a live gateway::

    franklinwh-direct-connect --host 10.100.1.1 power_flow
    franklinwh-direct-connect --host 10.100.1.1 call 1301
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys

import os as _os
import sys as _sys

from . import __version__, catalog, iter_pcap_frames
from .client import DirectConnectClient
from .transport import DEFAULT_RETRIES, DEFAULT_TIMEOUT, TransportError
from . import discover as _discover
from . import emulator as _emulator
from . import probe as _probe
from . import energy as _energy
from . import bms as _bms


def _load_frames(args: argparse.Namespace) -> list | None:
    """Read frames from a pcap with friendly errors instead of a traceback."""
    try:
        return list(iter_pcap_frames(args.pcap, cipher=not args.cleartext))
    except FileNotFoundError:
        print(f"error: no such file: {args.pcap}\n"
              f"  pass the path to a real capture (e.g. a tcpdump '-w' .pcap).",
              file=sys.stderr)
    except ValueError as e:
        print(f"error: {e}\n"
              f"  this reader needs a CLASSIC pcap — Wireshark saves .pcapng by "
              f"default, so 'Save As -> pcap', or capture with tcpdump -w.",
              file=sys.stderr)
    return None


def _cmd_decode(args: argparse.Namespace) -> int:
    frames = _load_frames(args)
    if frames is None:
        return 2
    if args.json:
        out = [
            {
                "cmdType": f.cmd_type,
                "dir": "REQ" if f.is_request else "RSP",
                "name": f.name,
                "snno": f.snno,
                "timeStamp": f.time_stamp,
                "verified": f.verify(),
                "dataArea": f.data_area,
            }
            for f in frames
        ]
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        for f in frames:
            flag = "" if f.verify() else "  [CRC/LEN MISMATCH]"
            print(f"{f.cmd_type} {'REQ' if f.is_request else 'RSP':<3} {f.name}{flag}")
            print(f"     {json.dumps(f.data_area)[:160]}")
    print(f"\n{len(frames)} frames", file=sys.stderr)
    return 0


def _known_codes() -> set[int]:
    """All cmdTypes the catalog knows (requests + their replies)."""
    return set(catalog.CATALOG) | {i.response for i in catalog.CATALOG.values()}


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Triage a pcap: which cmdTypes appear, and which are NOT yet cataloged.

    Unknown odd codes captured while driving the app are the candidate
    write/control codes — their dataArea carries the setpoint.
    """
    frames = _load_frames(args)
    if frames is None:
        return 2
    known = _known_codes()
    seen: dict[int, dict] = {}
    for f in frames:
        e = seen.setdefault(f.cmd_type, {"count": 0, "sample": f})
        e["count"] += 1
    rows = sorted(seen.items())
    if args.unknown:
        rows = [(c, e) for c, e in rows if c not in known]
    for cmd, e in rows:
        is_known = cmd in known
        tag = "" if is_known else "  UNKNOWN  <-- candidate write/control code"
        kind = "REQ" if cmd % 2 else "RSP"
        print(f"{cmd:<6} x{e['count']:<4} {kind}  {catalog.describe(cmd)}{tag}")
        if not is_known:
            print(f"       sample dataArea: {json.dumps(e['sample'].data_area)[:200]}")
    n_unknown = sum(1 for c in seen if c not in known)
    print(f"\n{len(frames)} frames, {len(seen)} distinct cmdTypes, "
          f"{n_unknown} unknown", file=sys.stderr)
    return 0


def _host_port(spec: str, default_port: int) -> tuple[str, int]:
    """Parse 'host' or 'host:port'."""
    if ":" in spec:
        host, _, port = spec.rpartition(":")
        return host, int(port)
    return spec, default_port


def _cmd_proxy(args: argparse.Namespace) -> int:
    """Run a transparent decoding relay between the app and a real aGate."""
    from . import proxy as _proxy

    target_host, target_port = _host_port(args.target, 9000)
    listen_host, listen_port = _host_port(args.listen, 9000)
    try:
        _proxy.serve(listen_host, listen_port, target_host, target_port,
                     once=args.once, record=args.record)
        if args.record:
            print(f"proxy: capture written to {args.record}", file=sys.stderr)
    except OSError as e:
        print(f"proxy error: {e}", file=sys.stderr)
        return 2
    return 0


def _catalog_flags(info) -> str:
    """Compact per-entry markers: writability and confidence."""
    marks = []
    if catalog.writes_for(info.request):
        marks.append("W")
    if info.request in catalog.UNCONFIRMED:
        marks.append("?")
    if info.request in catalog.MAINTENANCE:
        marks.append("!")
    return "".join(marks)


def _cmd_catalog(args: argparse.Namespace) -> int:
    """Render the cmdType catalog: grouped, wrapped, flagged."""
    import shutil
    import textwrap

    entries = sorted(catalog.CATALOG.values(), key=lambda i: i.request)
    if args.grep:
        needle = args.grep.lower()
        entries = [i for i in entries
                   if needle in i.name.lower()
                   or needle in i.description.lower()
                   or needle in (i.cloud_api or "").lower()
                   or needle == str(i.request)]
        if not entries:
            print(f"no catalog entry matches {args.grep!r}", file=sys.stderr)
            return 1

    if args.json:
        json.dump(
            [
                {
                    "request": i.request,
                    "response": i.response,
                    "name": i.name,
                    "description": i.description,
                    "cloud_api": i.cloud_api,
                    "family": catalog.family(i.request),
                    "writes": catalog.writes_for(i.request),
                    "unconfirmed": i.request in catalog.UNCONFIRMED,
                    "maintenance": i.request in catalog.MAINTENANCE,
                }
                for i in entries
            ],
            sys.stdout, indent=2,
        )
        print()
        return 0

    width = max(60, min(shutil.get_terminal_size((100, 24)).columns, 110))

    # Group first so each family's name column can be sized to its own widest
    # name — one global width would pad every short name out to the 30-char
    # grid_compliance_* entries.
    groups: dict[str, list] = {}
    for info in entries:
        groups.setdefault(catalog.family(info.request), []).append(info)

    for fam, members in groups.items():
        name_w = max(len(i.name) for i in members)
        lead = 2 + 4 + 4 + 4 + 2 + name_w + 2 + 3 + 1  # code -> code  name  flags
        desc_w = max(28, width - lead)
        print(f"\n{fam}")
        print("  " + "─" * (width - 2))
        for info in members:
            lines = textwrap.wrap(info.description, desc_w) or [""]
            print(f"  {info.request:<4} -> {info.response:<4}  {info.name:<{name_w}}  "
                  f"{_catalog_flags(info):<3} {lines[0]}")
            for cont in lines[1:]:
                print(" " * lead + cont)
            if info.cloud_api:
                print(" " * lead + f"cloud: {info.cloud_api}")

    total = len(catalog.CATALOG)
    shown = f"{len(entries)} of {total}" if len(entries) != total else str(total)
    mapped = sum(1 for i in entries if i.cloud_api)
    sys.stdout.flush()  # keep the stderr summary after the listing when piped
    print(f"\n{shown} cmdTypes ({mapped} with a known cloud equivalent).\n"
          f"Flags: W = write helper exists, ? = purpose UNCONFIRMED, "
          f"! = maintenance (the opt=0 read is safe).\n"
          f"Every name above is a live subcommand: "
          f"franklinwh-direct-connect -i <ip> <name>   (or: call <code>)", file=sys.stderr)
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    if args.targets in ("gateway", "hotspot"):
        gw = _discover.default_gateway()
        if not gw:
            print(
                "error: could not determine the hotspot gateway IP.\n"
                "  Make sure you are joined to the aGate WiFi hotspot "
                "(SSID AP_<serial>),\n"
                "  then retry. Or pass an explicit target: "
                "franklinwh-direct-connect scan 10.100.1.0/24",
                file=sys.stderr,
            )
            return 2
        targets = [gw]
        print(f"scanning hotspot gateway {gw}", file=sys.stderr)
    else:
        try:
            targets = _discover.expand_targets(args.targets)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    if len(targets) > 4096:
        print(f"error: {len(targets)} hosts is a lot; narrow the range", file=sys.stderr)
        return 2
    print(f"scanning {len(targets)} host(s) …", file=sys.stderr)
    try:
        results = _discover.scan(
            targets, timeout=args.timeout, workers=args.workers, probe=not args.no_probe
        )
    except KeyboardInterrupt:
        print("\nscan interrupted.", file=sys.stderr)
        return 130  # conventional exit code for Ctrl-C
    if args.json:
        out = [
            {
                "host": r.host,
                "sendmqtt_open": r.sendmqtt_open,
                "sendmqtt_confirmed": r.sendmqtt_confirmed,
                "modbus_open": r.modbus_open,
                "modbus_confirmed": r.modbus_confirmed,
                "manifest": r.manifest,
            }
            for r in results
        ]
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        for r in results:
            print(r.summary())
    print(f"\nscanned {len(targets)} host(s), {len(results)} with FranklinWH ports open",
          file=sys.stderr)
    return 0


def _cmd_emulate(args: argparse.Namespace) -> int:
    return _emulator.run(
        args.bind, args.port, args.equip or _emulator.DEFAULT_EQUIP,
        seed=args.seed, serial=args.serial, dynamic=not args.static,
        units=args.units,
    )


def _wait_port(host: str, port: int, *, want_up: bool, timeout: float,
               interval: float = 3.0) -> bool:
    """Poll a TCP port until it matches ``want_up`` (open/closed) or ``timeout`` elapses.

    der_comms writes can be delayed-apply (the service changes state a few seconds after
    the write, no reboot), so verification must poll for the expected state, not check once.
    """
    import time
    deadline = time.time() + timeout
    while True:
        if _discover.port_open(host, port, timeout=2.0) == want_up:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def _der_print(result) -> None:
    print(f"SunSpec Modbus (sunsMdEn): {'on' if result.get('sunsMdEn') else 'off'}"
          f"  (tcp {result.get('ip')}:{result.get('port')})")
    print(f"IEEE 2030.5 / SEP2 (enable): {'on' if result.get('enable') else 'off'}"
          f"  (status2030_5={result.get('status2030_5')}, registered="
          f"{'yes' if result.get('lfdi') else 'no'})")


_SEP2_ON_WARNING = (
    "WARNING: enabling IEEE 2030.5 / SEP2 lets an external utility / DERMS server dispatch\n"
    "   your battery once the aGate registers with it. Only enable if you intend that.\n"
)


def _confirm(prompt: str, force: bool) -> bool:
    if force:
        return True
    try:
        return input(prompt).strip().lower() == "yes"
    except EOFError:
        return False


def _cmd_der_comms(args: argparse.Namespace) -> int:
    """Show DER comms config, or write it (SunSpec Modbus / IEEE 2030.5).

    Writes use full-block read-modify-write and are verified at the INTERFACE level, not
    the config field: Modbus by the actual :502 service, 2030.5 by registration state.
    The Modbus write is asymmetric — turning it OFF stops :502 immediately, turning it ON
    only sets a flag that binds :502 on the next reboot (use --and-reboot).
    """
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    set_modbus = getattr(args, "set_modbus", None)
    set_2030_5 = getattr(args, "set_2030_5", None)
    force = getattr(args, "force", False)

    # Confirmations before connecting (destructive / hands-off-control).
    if set_modbus == "off" and not _confirm(
            "Turn OFF SunSpec Modbus? This stops :502 and strands Modbus tooling; it only "
            "comes back on a reboot. Type 'yes': ", force):
        print("aborted: Modbus not changed.", file=sys.stderr); return 2
    if set_2030_5 == "on":
        print(_SEP2_ON_WARNING, file=sys.stderr)
        if not _confirm("Enable IEEE 2030.5 / SEP2? Type 'yes': ", force):
            print("aborted: 2030.5 not changed.", file=sys.stderr); return 2

    host, port = args.host, args.port
    try:
        with DirectConnectClient(host, port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            if set_modbus is None and set_2030_5 is None:          # read
                result = c.der_comms()
                if args.json:
                    json.dump(result, sys.stdout, indent=2); print()
                else:
                    _der_print(result)
                return 0

            reply = c.set_der_comms(                                # full-block RMW
                sunspec_modbus=None if set_modbus is None else (set_modbus == "on"),
                sep2=None if set_2030_5 is None else (set_2030_5 == "on"),
            )
            rc = 0
            # -- interface-level verification (NOT the config field) --
            # The write is DELAYED-APPLY on some firmware (:502 changes state a few seconds
            # later, no reboot) and reboot-to-apply on others — so POLL :502 over a window
            # for the expected state rather than checking once.
            if set_modbus == "off":
                stopped = _wait_port(host, 502, want_up=False, timeout=30.0)
                if stopped:
                    print("SunSpec Modbus OFF: verified :502 stopped.")
                else:
                    print("WARNING: wrote sunsMdEn=0 but :502 is still UP after 30s — on "
                          "some firmware this needs a reboot to apply.", file=sys.stderr)
                    rc = 1
            elif set_modbus == "on":
                bound = _wait_port(host, 502, want_up=True, timeout=30.0)
                if bound:
                    print("SunSpec Modbus ON: verified :502 up.")
                elif getattr(args, "and_reboot", False):
                    print("sunsMdEn=1 set but :502 not up yet; rebooting to bind it...",
                          file=sys.stderr)
                    return _reboot_then_verify_502(args, host, port)
                else:
                    print("WARNING: wrote sunsMdEn=1 but :502 is not up after 30s — on some "
                          "firmware this needs a reboot; re-run with --and-reboot.",
                          file=sys.stderr)
                    rc = 1
            if set_2030_5 is not None:
                after = c.der_comms()
                if set_2030_5 == "on":
                    reg = "registered" if after.get("lfdi") else "enabled but NOT registered"
                    print(f"IEEE 2030.5 enable=1: {reg} "
                          f"(status2030_5={after.get('status2030_5')}).")
                else:
                    ok = not after.get("enable")
                    print(f"IEEE 2030.5 OFF: {'verified (enable=0)' if ok else 'NOT verified'}.")
                    rc = rc or (0 if ok else 1)
            return rc
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _reboot_then_verify_502(args, host, port) -> int:
    """Reboot the aGate and confirm Modbus :502 comes back (for --set-modbus on --and-reboot)."""
    try:
        with DirectConnectClient(host, port, timeout=args.timeout, retries=0,
                         equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            c.reboot()
    except (OSError, TransportError, TimeoutError):
        pass
    rc = _wait_for_reboot(args, host, port, wait=getattr(args, "wait", 0) or 300)
    if rc == 0:
        up = any(_discover.port_open(host, 502, timeout=3.0) for _ in range(3))
        print(f"Modbus :502 {'UP (verified)' if up else 'still DOWN'} after reboot.")
        return 0 if up else 1
    return rc


def _cmd_health(args: argparse.Namespace) -> int:
    """Health check: which listeners/services are up on the aGate.

    Checks the sendMqtt (:9000) and Modbus (:502) TCP listeners, whether a sendMqtt
    login succeeds, and what der_comms (1205) reports for the Modbus/2030.5 config —
    so a config flag can be compared against the actual :502 service (they can disagree).
    Exit 0 if sendMqtt is serving, else 1.
    """
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    import time
    host, port = args.host, args.port
    checks: dict = {}
    # ping is INFORMATIONAL only — on a lossy link a single ICMP packet often drops even
    # though the aGate is reachable (the protocol round-trip below is the real check).
    checks["ping"] = _discover.ping(host, timeout=1.0)
    # :502 (Modbus) — best-effort TCP, a few attempts to ride out packet loss.
    checks["modbus_502"] = any(_discover.port_open(host, 502, timeout=3.0) for _ in range(3))
    # Authoritative: a real sendMqtt round-trip WITH retries, and its latency.
    checks["sendmqtt_9000"] = False
    checks["latency_ms"] = None
    checks["sunsMdEn"] = None
    try:
        with DirectConnectClient(host, port, timeout=15.0, retries=3, equip_no=args.equip) as c:
            t0 = time.time()
            if args.equip is None:
                c.login()
            else:
                c.power_flow()                          # force a round-trip to time it
            checks["latency_ms"] = round((time.time() - t0) * 1000, 1)
            checks["sendmqtt_9000"] = True
            try:
                checks["sunsMdEn"] = c.der_comms().get("sunsMdEn")
            except (OSError, TransportError, TimeoutError):
                pass
    except (OSError, TransportError, TimeoutError):
        pass

    if args.json:
        json.dump(checks, sys.stdout, indent=2); print()
    else:
        def mark(b): return "UP" if b else "DOWN"
        lat = "" if checks["latency_ms"] is None else f"  {checks['latency_ms']}ms"
        ping = "reply" if checks["ping"] else ("no-reply" if checks["ping"] is False else "n/a")
        print(f"aGate {host} health:")
        print(f"  ping             {ping}")
        print(f"  sendMqtt :9000   Test {'OK' if checks['sendmqtt_9000'] else 'FAILED'}{lat}")
        print(f"  Modbus   :502    {mark(checks['modbus_502'])}")
        cfg = checks["sunsMdEn"]
        cfg_s = "unknown" if cfg is None else ("on" if cfg else "off")
        note = ""
        if cfg == 1 and not checks["modbus_502"]:
            note = "  WARNING: config says ON but :502 is DOWN (a reboot re-binds it on boot)"
        elif cfg == 0 and checks["modbus_502"]:
            note = "  WARNING: config says OFF but :502 is UP"
        print(f"  Modbus config    sunsMdEn={cfg_s}{note}")
        if not checks["sendmqtt_9000"]:
            print(f"  hint: no sendMqtt round-trip — if ping also fails the aGate may be "
                  f"off-LAN (4G failover) or on a new IP; re-discover with "
                  f"'franklinwh-direct-connect scan <subnet>'.")
    return 0 if checks["sendmqtt_9000"] else 1


def _cmd_firmware(args: argparse.Namespace) -> int:
    """Show the aGate firmware/version block (from the login manifest). Read-only."""
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            fw = c.firmware()
            if args.json:
                json.dump(fw, sys.stdout, indent=2); print()
            else:
                for k in c.FIRMWARE_FIELDS:
                    if k in fw:
                        print(f"  {k:<14} {fw[k]}")
            return 0
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


_REBOOT_WARNING = (
    "WARNING: this REBOOTS the aGate. All connections drop for ~1-2 minutes\n"
    "   (sendMqtt :9000 and Modbus :502); the battery keeps running on its own.\n"
    "   On boot the aGate reloads saved config (re-binds Modbus :502 if enabled).\n"
)


def _reboot_4g_warning(c) -> None:
    """Warn if 4G is enabled — a reboot can fail over to cellular and leave the LAN."""
    try:
        sw = c.network_switches()
        if sw.get("4GNetSwitch"):
            print("   NOTE: 4G is enabled on this aGate; after a reboot it may fail over "
                  "to cellular and briefly leave the LAN (it will return on WiFi/eth, "
                  "possibly on a new IP).", file=sys.stderr)
    except (OSError, TransportError, TimeoutError):
        pass


def _cmd_reboot(args: argparse.Namespace) -> int:
    """Reboot the aGate (cmd 1721). Confirms unless --force; --wait verifies it returns."""
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    host, port = args.host, args.port
    wait = getattr(args, "wait", None)   # None = don't wait; 0 = forever; N = seconds

    # Pre-flight: capture net state and warn about 4G before the confirmation.
    try:
        with DirectConnectClient(host, port, timeout=args.timeout, retries=args.retries,
                         equip_no=args.equip) as pre:
            if args.equip is None:
                pre.login()
            _reboot_4g_warning(pre)
    except (OSError, TransportError, TimeoutError):
        pass

    if not args.force:
        print(_REBOOT_WARNING, file=sys.stderr)
        try:
            reply = input("Reboot the aGate? Type 'yes' to proceed: ").strip().lower()
        except EOFError:
            reply = ""
        if reply != "yes":
            print("aborted: aGate not rebooted (use --force to skip this prompt).",
                  file=sys.stderr)
            return 2

    try:
        # retries=0: the socket drops on reboot; don't spin trying to reconnect.
        with DirectConnectClient(host, port, timeout=args.timeout,
                         retries=0, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            result = c.reboot()
    except (OSError, TransportError, TimeoutError) as e:
        result = {"dropped": True, "detail": str(e)}
    if result.get("dropped"):
        print("reboot command sent; aGate dropped the connection (expected).")
    else:
        print(f"reboot command sent: result={result.get('result')}.")

    if wait is None:
        print("Give it ~1-2 min to come back (or use --wait to poll).")
        return 0
    return _wait_for_reboot(args, host, port, wait)


def _wait_for_reboot(args, host: str, port: int, wait: int) -> int:
    """Verify the reboot: watch :9000 go DOWN then come back UP + login. If it does not
    return on the same IP within budget, scan the subnet to re-discover it (a reboot can
    land a new DHCP lease or fail over to 4G). Returns 0 on confirmed return, else 1."""
    import time
    start = time.time()
    deadline = None if wait == 0 else start + wait

    print("waiting for aGate to go OFFLINE (proof it actually rebooted)...", file=sys.stderr)
    down_cap = 90.0 if deadline is None else min(90.0, max(1.0, deadline - time.time()))
    down_deadline = time.time() + down_cap
    went_down = False
    while time.time() < down_deadline:
        if not _discover.port_open(host, port, timeout=2.0):
            went_down = True
            break
        time.sleep(3)
    if not went_down:
        print(f"WARNING: aGate never went offline within {int(down_cap)}s — the reboot "
              "appears to have had NO effect.", file=sys.stderr)
        return 1
    print(f"  aGate OFFLINE at t+{int(time.time() - start)}s — reboot confirmed. "
          "waiting for it to return...", file=sys.stderr)

    EST = 120.0
    while True:
        el = time.time() - start
        if _discover.port_open(host, port, timeout=2.0):
            try:
                with DirectConnectClient(host, port, timeout=8.0, retries=1,
                                 equip_no=args.equip) as c2:
                    if args.equip is None:
                        c2.login()
                modbus = _discover.port_open(host, 502, timeout=3.0)
                print(f"aGate back ONLINE after {int(el)}s (:9000 login OK). "
                      f"Modbus :502 {'UP' if modbus else 'still DOWN'}.")
                return 0
            except (OSError, TransportError, TimeoutError):
                pass                                    # port up but broker not ready yet
        if deadline is not None and time.time() >= deadline:
            print(f"aGate did not return on {host} after {int(el)}s. It may have rebooted "
                  "onto a new IP or failed over to 4G — scanning the subnet...", file=sys.stderr)
            return _rediscover(host)
        pct = min(99, int(el / EST * 100))
        print(f"  [{int(el):>3}s] ~{pct}%  still booting...", file=sys.stderr, flush=True)
        time.sleep(8)


def _rediscover(host: str) -> int:
    """Scan the host's /24 to re-find the aGate after a reboot moved it."""
    try:
        subnet = host.rsplit(".", 1)[0] + ".0/24"
        targets = _discover.expand_targets(subnet)
    except ValueError:
        print("  could not derive a subnet to scan.", file=sys.stderr)
        return 1
    print(f"  scanning {subnet} for the aGate...", file=sys.stderr)
    found = _discover.scan(targets, timeout=1.0, probe=True)
    hits = [r for r in found if getattr(r, "sendmqtt_confirmed", False)]
    if hits:
        for r in hits:
            print(f"  found aGate at {r.host} (IBG_SN={ (r.manifest or {}).get('IBG_SN') })")
        return 0
    print("  aGate not found on the subnet yet — it may still be booting or on 4G. "
          "Retry 'franklinwh-direct-connect scan <subnet>' shortly.", file=sys.stderr)
    return 1


def _cmd_grid_profile(args: argparse.Namespace) -> int:
    """Fetch the full grid-compliance profile (25 cmdType fan-out)."""
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout, retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            result = c.grid_profile()
            json.dump(result, sys.stdout, indent=2)
            print()
            return 0
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _cmd_control(args: argparse.Namespace) -> int:
    """Live get-or-set for 'mode' and 'offgrid'. Requires --host/-i."""
    if not args.host:
        print("error: --host/-i is required for live commands", file=sys.stderr)
        return 2
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout, retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()

            if args.command == "mode":
                if args.set is None:  # read
                    if args.raw:  # full on-the-wire frame (envelope + dataArea)
                        fr = c.transport.request(catalog.Cmd.MODE_LIST, c.equip_no, {"opt": 1})
                        json.dump(fr.raw_json, sys.stdout, indent=2); print()
                        return 0
                    ml = c.mode_list()
                    if args.json:  # decoded dataArea only
                        json.dump(ml, sys.stdout, indent=2); print()
                        return 0
                    cur = ml.get("current_id")
                    if args.list:  # opt-in: all modes + details
                        for m in ml.get("list", []):
                            mark = "  <- active" if m.get("id") == cur else ""
                            label = catalog.mode_label(m)
                            raw = m.get("name", "")
                            tariff = f"  [{raw}]" if raw and raw != label else ""
                            print(f"  id={m.get('id'):<7} {label:<18} "
                                  f"reserve={m.get('reserved_soc')}% "
                                  f"workMode={m.get('scheduling_type')}{tariff}{mark}")
                    else:  # default: just the current mode (canonical name)
                        active = next((m for m in ml.get("list", []) if m.get("id") == cur), {})
                        print(f"{catalog.mode_label(active)} (id {cur})")
                    return 0
                before = c.mode_list().get("current_id")
                reply = c.set_mode(args.set)
                after = c.mode_list().get("current_id")
                if args.json:
                    out: dict = {"set": args.set, "result": reply.get("result"),
                                 "current_id_before": before, "current_id_after": after}
                    json.dump(out, sys.stdout); print()
                else:
                    print(f"mode --set {args.set}: result={reply.get('result')}  "
                          f"current_id {before} -> {after}")
                return 0 if reply.get("result") == 0 else 1

            # offgrid
            if args.set is None:  # read
                if args.raw:  # full on-the-wire frame
                    fr = c.transport.request(catalog.Cmd.OFFGRID, c.equip_no, {"opt": 0})
                    json.dump(fr.raw_json, sys.stdout, indent=2); print()
                    return 0
                og = c.offgrid()
                if args.json:
                    json.dump(og, sys.stdout, indent=2); print()
                else:
                    print(f"offgrid: set={og.get('offgridSet')} "
                          f"soc={og.get('offgridSoc')} state={og.get('offgridState')}")
                return 0
            reply = c.set_offgrid(args.set == "on", soc=args.soc)
            print(f"offgrid --set {args.set} (soc={args.soc}): "
                  f"result={reply.get('result')} reason={reply.get('reason')}")
            return 0 if reply.get("result") == 0 else 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _run_once(c: DirectConnectClient, args: argparse.Namespace) -> dict:
    if args.command == "call":
        if args.cmd_type is None:
            raise ValueError("'call' needs a CMD_TYPE")
        data = json.loads(args.data) if args.data else None
        return c.call(args.cmd_type, data)
    cmd = getattr(args, "catalog_cmd", None)
    if cmd in catalog.NEEDS_DATE:
        return c.call(cmd, {"opt": 0, "date": args.date})
    if cmd in catalog.NEEDS_ID:
        # Per-device read: the request must name which device, or the aGate
        # returns an empty shell (result=1 reason=-1).
        return c.call(cmd, {"opt": 0, "id": args.id})
    method = getattr(c, args.command, None)
    if method is not None:
        return method()
    # Auto-wired catalog read with no hand-written DirectConnectClient method.
    return c.call(cmd)


def _parse_codes(spec: str) -> list[int]:
    """Parse '1413-1699' / '1207,1209' / '1500' into a list of odd request codes."""
    codes: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            codes.extend(_probe.gap_codes(int(lo), int(hi), include_known=True))
        else:
            codes.append(int(part))
    return codes


def _cmd_probe(args: argparse.Namespace) -> int:
    """Sweep cmdType codes against a live aGate, trying several payload shapes."""
    if not args.host:
        print("error: --host/-i is required for probe", file=sys.stderr)
        return 2

    if args.codes:
        codes = _parse_codes(args.codes)
    else:
        codes = _probe.gap_codes(args.start, args.end, include_known=args.include_known)

    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()

            serials = list(args.serial or [])
            if not serials and not args.no_serials:
                serials = _probe.discover_serials(c)
                print(f"discovered {len(serials)} battery serial(s): "
                      f"{', '.join(serials) or 'none'}", file=sys.stderr)

            if args.payload:
                try:
                    templates = [json.loads(p) for p in args.payload]
                except json.JSONDecodeError as e:
                    print(f"error: --payload must be JSON: {e}", file=sys.stderr)
                    return 2
                if not all(isinstance(t, dict) for t in templates):
                    print("error: --payload must be a JSON object", file=sys.stderr)
                    return 2
                payloads = _probe.expand_payloads(templates, serials)
            elif args.plain_only:
                payloads = [{"opt": 0}]
            else:
                payloads = _probe.default_payloads(serials)
            for shape in payloads:
                if shape.get("opt") not in (0, None):
                    print(f"error: refusing to send a non-read payload: {shape} "
                          f"(opt must be 0 or absent; opt=1 is the WRITE convention)",
                          file=sys.stderr)
                    return 2
            print(f"probing {len(codes)} cmdType(s) x {len(payloads)} payload shape(s) "
                  f"on {args.host} (timeout={args.timeout:g}s)\n", file=sys.stderr)

            results: list = []

            def _report(r) -> None:
                results.append(r)
                if args.json:
                    return
                if r.status != "hit" and not args.verbose:
                    return
                print(r.summary(), flush=True)
                if args.all_shapes:
                    for a in r.attempts:
                        shape = json.dumps(a["payload"], separators=(",", ":"))
                        detail = (f"{len(a.get('keys', []))} keys: "
                                  f"{', '.join(a.get('keys') or []) or '-'}"
                                  if a["status"] in ("hit", "empty")
                                  else a.get("error", a["status"]))
                        print(f"         {shape:<46} {a['status']:<8} {detail}",
                              flush=True)

            def _reconnect():
                """Rebuild the session — the aGate drops it on out-of-band codes."""
                try:
                    c.transport.close()
                except Exception:  # noqa: BLE001
                    pass
                c.transport.connect()
                if args.equip is None:
                    c.login()
                return c

            try:
                _probe.probe_codes(c, codes, payloads,
                                   stop_on_hit=not args.all_shapes,
                                   reconnect=_reconnect,
                                   on_result=_report)
            except KeyboardInterrupt:
                print("\nprobe interrupted.", file=sys.stderr)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        json.dump(
            [
                {
                    "cmdType": r.cmd_type, "status": r.status, "known": r.known,
                    "name": r.name if r.known else None,
                    "payload": r.payload, "keys": r.keys,
                    "cell_series": r.cell_series, "data": r.data,
                    "error": r.error, "attempts": r.attempts,
                }
                for r in results
            ],
            sys.stdout, indent=2,
        )
        print()

    rejected = [r for r in results if r.status == "rejected"]
    hits = [r for r in results if r.status == "hit"]
    new_hits = [r for r in hits if not r.known]
    cells = [r for r in hits if r.cell_series]
    selector = [r for r in hits if r.payload and "fhpSn" in r.payload]
    sys.stdout.flush()
    print(f"\n{len(results)} probed, {len(hits)} responded with data, "
          f"{len(new_hits)} NOT in the catalog "
          f"({len(rejected)} explicitly rejected as unimplemented).", file=sys.stderr)
    if selector:
        print(f"{len(selector)} needed an fhpSn selector — a plain opt=0 sweep would "
              f"have missed these: {', '.join(str(r.cmd_type) for r in selector)}",
              file=sys.stderr)
    if cells:
        print(f"CELL-TELEMETRY CANDIDATES: "
              f"{', '.join(str(r.cmd_type) for r in cells)}", file=sys.stderr)
    return 0


def _cmd_tou(args: argparse.Namespace) -> int:
    """Show the gateway's TOU tariff schedule as readable blocks."""
    if not args.host:
        print("error: --host/-i is required", file=sys.stderr)
        return 2
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            payload = c.tou_schedule()
            when = c.time_location()
    except (OSError, TransportError, TimeoutError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        json.dump({
            "touStrategy": payload.get("touStrategy"),
            "time": when.get("time"),
            "timezone": when.get("timezone"),
            "DST": when.get("DST"),
            "schedule": {
                day: [{"start": b.start, "end": b.end,
                       "wave": b.wave, "wave_name": b.wave_name}
                      for b in _energy.decode_tou(payload, day)]
                for day in ("workday", "weekend")
            },
        }, sys.stdout, indent=2)
        print()
        return 0

    now = when.get("time", "")
    dow = ""
    try:
        import datetime as _dt
        parsed = _dt.datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
        dow = parsed.strftime("%A")
    except (ValueError, TypeError):
        pass
    print(f"gateway time: {now} {dow}  (UTC+{when.get('timezone')}, "
          f"DST={'on' if when.get('DST') else 'off'})")
    print(f"touStrategy:  {payload.get('touStrategy')}\n")

    for day in ("workday", "weekend"):
        blocks = _energy.decode_tou(payload, day)
        count = payload.get(f"{day}Lv")
        print(f"{day} ({count} block{'s' if count != 1 else ''})")
        if not blocks:
            print("  (none)")
        for b in blocks:
            bar = "" if not args.bar else "  " + _tou_bar(b)
            print(f"  {b.start}–{b.end:<6} tier {b.wave} {b.wave_name}{bar}")
        print()
    sys.stdout.flush()
    print("Tariff (wave) schedule only. The per-block DISPATCH action the app shows "
          "alongside it is NOT on the local channel — 1407 has no sub-type carrying "
          "it (tested opt=0 with type/paraType/dispatch variants).", file=sys.stderr)
    return 0


def _tou_bar(block) -> str:
    """Crude 24-column bar showing where a block sits in the day."""
    def _col(hhmm: str) -> int:
        try:
            h, m = hhmm.split(":")
            return min(24, int(h) + (1 if int(m) else 0))
        except ValueError:
            return 0
    lo, hi = _col(block.start), _col(block.end)
    return "".join("#" if lo <= i < max(hi, lo + 1) else "." for i in range(24))


def _cmd_energy_rollup(args: argparse.Namespace) -> int:
    """Aggregate daily energy history into week/month/year/total locally."""
    if not args.host:
        print("error: --host/-i is required", file=sys.stderr)
        return 2
    import datetime as _dt
    try:
        target = (_dt.date.fromisoformat(args.date) if args.date
                  else _dt.date.today())
    except ValueError:
        print(f"error: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 2

    start, end = _energy.period_range(args.period, target)
    n_days = (end - start).days + 1
    print(f"rolling up {args.period}: {start} .. {end} ({n_days} day"
          f"{'s' if n_days != 1 else ''}), one request per day …", file=sys.stderr)

    def _tick(day, payload):
        if not args.quiet:
            mark = "." if _energy.has_data(payload) else "_"
            print(mark, end="", flush=True, file=sys.stderr)

    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            roll = _energy.rollup(lambda d: c.energy_history(d), args.period,
                                  target, on_day=_tick,
                                  stop_after_empty=args.stop_after_empty)
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        return 130
    except (OSError, TransportError, TimeoutError, ValueError) as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(file=sys.stderr)

    if args.json:
        json.dump(roll.as_dict(), sys.stdout, indent=2)
        print()
        return 0

    print(f"\n{roll.summary()}\n")
    label_w = max(len(c) for c in catalog.ENERGY_CHANNELS)
    header = f"{'channel':<{label_w}}  {'total':>10}" + "".join(
        f"{t:>10}" for t in _energy.TIERS)
    print(header)
    print("-" * len(header))
    for channel in catalog.ENERGY_CHANNELS:
        row = f"{channel:<{label_w}}  {roll.totals[channel]:>10.4f}"
        row += "".join(f"{roll.tiers[t][channel]:>10.4f}" for t in _energy.TIERS)
        print(row)
    sys.stdout.flush()
    print(f"\nkWh. Tier columns split each channel by TOU tariff "
          f"(see 'franklinwh-direct-connect -i <ip> tou').", file=sys.stderr)
    if not roll.complete:
        print(f"{len(roll.days_missing)} day(s) had no stored history — the aGate "
              f"keeps a rolling window of roughly 105 days.", file=sys.stderr)
    return 0


def _cmd_battery(args: argparse.Namespace) -> int:
    """Battery Management view — per-cell telemetry, pack health, bus rails."""
    if not args.host:
        print("error: --host/-i is required", file=sys.stderr)
        return 2
    import time as _t

    try:
        duration = _bms.parse_duration(args.duration) if args.duration else None
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    interval = args.watch if args.watch is not None else (5.0 if duration else None)
    colour = _bms.use_colour() and not args.no_colour
    # Only repaint in place for an interactive terminal; piped output appends so a
    # log or a file keeps every sample instead of a pile of escape codes.
    repaint = colour and interval is not None

    def _read(c):
        return {
            "cells": c.battery_cells(args.id),
            "pe": c.power_electronics(args.id),
            "states": c.device_states(args.id),
            "firmware": c.device_firmware(args.id),
            "check": c.device_check(),
        }

    started = _t.time()
    shown = 0
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout,
                         retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()
            while True:
                try:
                    data = _read(c)
                except (OSError, TransportError, TimeoutError, ValueError) as e:
                    if interval is None:
                        raise
                    # A dropped read must not end a monitoring session — this link
                    # is flaky by nature. Report and keep the session going.
                    print(f"{_t.strftime('%H:%M:%S')}  read failed: {e}",
                          file=sys.stderr, flush=True)
                    _t.sleep(interval)
                    continue

                if args.json:
                    json.dump({**data, "ts": int(_t.time())}, sys.stdout, indent=2)
                    print(flush=True)
                else:
                    if repaint:
                        sys.stdout.write("\033[H\033[J")   # home + clear
                    lines = _bms.render(
                        data["cells"], data["pe"], data["states"],
                        data["firmware"], data["check"],
                        colour=colour, dev_id=args.id,
                        when=_t.strftime("%Y-%m-%d %H:%M:%S"))
                    print("\n".join(lines), flush=True)
                shown += 1

                if interval is None:
                    break
                if args.count and shown >= args.count:
                    break
                if duration and (_t.time() - started) >= duration:
                    break
                _t.sleep(interval)
    except KeyboardInterrupt:
        print()
        return 0
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if interval is not None and not args.json:
        print(f"{shown} sample(s).", file=sys.stderr)
    return 0


def _watch_line(command: str, result: dict) -> str:
    """One compact line per poll, with a friendly summary for power_flow."""
    import time as _t
    ts = _t.strftime("%H:%M:%S")
    if command == "power_flow":
        g = result.get
        return (f"{ts}  soc={g('soc')}%  grid={g('p_uti')}W  solar={g('p_sun')}W  "
                f"batt={g('p_fhp')}W  load={g('p_load')}W  mode={g('name')}")
    # generic: compact single-line JSON
    return f"{ts}  {json.dumps(result, separators=(',', ':'))}"


def _cmd_live(args: argparse.Namespace) -> int:
    if not args.host:
        print("error: --host is required for live commands", file=sys.stderr)
        return 2
    try:
        with DirectConnectClient(args.host, args.port, timeout=args.timeout, retries=args.retries, equip_no=args.equip) as c:
            if args.equip is None:
                c.login()

            if args.watch is None:
                result = _run_once(c, args)
                json.dump(result, sys.stdout, indent=2)
                print()
                return 0

            # --watch: reuse the one logged-in connection and poll on an interval.
            import time as _t
            n = 0
            print(f"watching {args.command} every {args.watch}s "
                  f"(Ctrl-C to stop){'' if not args.count else f', {args.count} samples'}",
                  file=sys.stderr)
            while True:
                try:
                    print(_watch_line(args.command, _run_once(c, args)), flush=True)
                except Exception as e:
                    print(f"{_t.strftime('%H:%M:%S')}  poll error: {e}", file=sys.stderr)
                n += 1
                if args.count and n >= args.count:
                    break
                _t.sleep(args.watch)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, TransportError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"  hint: is the aGate reachable? try 'franklinwh-direct-connect health --host "
              f"{args.host}' or re-discover with 'franklinwh-direct-connect scan <subnet>' "
              f"(it may have rebooted onto a new IP).", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


# Subcommands that are NOT plain catalog reads: 'call' is the raw escape hatch,
# and these names have dedicated get-or-set subparsers built further down.
_EXTRA_LIVE_COMMANDS = ["call"]
_DEDICATED = {"mode", "mode_page", "offgrid", "der_comms"}


def live_commands() -> list[str]:
    """Read subcommands, DERIVED from ``catalog.CATALOG``.

    Generated rather than hand-listed so the command surface and the catalog
    cannot drift — every catalog name is guaranteed to be typeable, and a new
    ``CATALOG`` row becomes a working subcommand with no CLI edit. (This list
    used to be maintained by hand and had fallen 32 names behind; see
    BACKLOG DEF-CLI-CATALOG-DRIFT.)
    """
    names = [i.name for i in sorted(catalog.CATALOG.values(), key=lambda i: i.request)
             if i.name not in _DEDICATED]
    return names + _EXTRA_LIVE_COMMANDS


#: Back-compat alias — was a hand-maintained list, now derived.
LIVE_COMMANDS = live_commands()


def _commands_epilog() -> str:
    """Grouped listing of the auto-wired catalog reads for the main --help.

    With one subcommand per catalog entry, a flat argparse listing would be 60+
    lines. Group them by family and point at 'catalog' for the detail.
    """
    import textwrap

    by_name = {i.name: i for i in catalog.CATALOG.values()}
    groups: dict[str, list[str]] = {}
    for name in live_commands():
        info = by_name.get(name)
        if info is None:
            continue
        groups.setdefault(catalog.family(info.request), []).append(name)

    out = [f"live reads ({sum(len(v) for v in groups.values())} commands, one per cmdType) —"
           f" each needs -i/--ip; all accept --watch/--count:"]
    label_w = max(len(g) for g in groups) + 2
    for fam, names in groups.items():
        body = textwrap.wrap(", ".join(names), 96 - label_w) or [""]
        out.append(f"  {fam:<{label_w}}{body[0]}")
        out.extend(" " * (2 + label_w) + line for line in body[1:])
    out.append("")
    out.append("Run 'franklinwh-direct-connect catalog' for cmdType codes, cloud equivalents and")
    out.append("descriptions, or 'franklinwh-direct-connect <command> --help' for one command.")
    return "\n".join(out)


class _FriendlyParser(argparse.ArgumentParser):
    """ArgumentParser that turns 'invalid choice' into an actionable message.

    The stock message dumps all 70+ subcommand names twice and never mentions
    that an uncataloged or unwrapped cmdType can still be reached via 'call'.
    """

    def error(self, message: str):  # noqa: D102 - argparse override
        m = re.match(r"argument <command>: invalid choice: '([^']*)'", message)
        if m is None:
            super().error(message)
        bad = m.group(1)
        print(f"error: '{bad}' is not a franklinwh-direct-connect command.\n", file=sys.stderr)

        choices = sorted(
            c for act in self._subparsers._group_actions for c in act.choices
        ) if self._subparsers else []
        near = difflib.get_close_matches(bad, choices, n=5, cutoff=0.5)
        if near:
            print("did you mean:", file=sys.stderr)
            for n in near:
                print(f"  franklinwh-direct-connect {n}", file=sys.stderr)
            print(file=sys.stderr)

        if bad.isdigit():
            code = int(bad)
            info = catalog.CATALOG.get(code)
            named = f" ({info.name})" if info else ""
            print(f"'{bad}' looks like a cmdType{named} — call it directly:\n"
                  f"  franklinwh-direct-connect -i <ip> call {bad}\n", file=sys.stderr)

        print("Run 'franklinwh-direct-connect --help' for the command list, or\n"
              "    'franklinwh-direct-connect catalog' to browse cmdTypes.", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    # Take the name the user actually invoked, so usage/--version read correctly
    # under either entry point (franklinwh-direct-connect or the deprecated
    # franklinwh-direct-connect) and under `python -m`.
    prog = _os.path.basename(_sys.argv[0]) or "franklinwh-direct-connect"
    if prog in ("__main__.py", "-c", "python", "python3"):
        prog = "franklinwh-direct-connect"
    p = _FriendlyParser(prog=prog, description=__doc__,
                        epilog=_commands_epilog(),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # -i/--ip mirrors the franklinwh-modbus CLI; --host kept as an alias.
    p.add_argument("--host", "-i", "--ip", dest="host",
                   help="aGate broker host/IP for live commands")
    p.add_argument("--port", "-p", type=int, default=9000)
    p.add_argument("--equip", help="equipNo (skip login if provided)")
    p.add_argument("--timeout", "-t", type=float, default=DEFAULT_TIMEOUT,
                   help=f"per-request timeout in seconds (default {DEFAULT_TIMEOUT:g}; "
                        "raise for slow wifi)")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                   help=f"transient reconnect-retries per request/login "
                        f"(default {DEFAULT_RETRIES}; raise for flaky wifi)")

    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    d = sub.add_parser("decode", help="decode frames from a pcap file")
    d.add_argument("pcap")
    d.add_argument("--json", action="store_true", help="emit JSON")
    d.add_argument("--cleartext", action="store_true", help="cloud-REST variant (no cipher)")
    d.set_defaults(func=_cmd_decode)

    an = sub.add_parser("analyze", help="triage a pcap: list cmdTypes, flag unknown (write) codes")
    an.add_argument("pcap")
    an.add_argument("--unknown", action="store_true", help="show only un-cataloged cmdTypes")
    an.add_argument("--cleartext", action="store_true", help="cloud-REST variant (no cipher)")
    an.set_defaults(func=_cmd_analyze)

    px = sub.add_parser("proxy", help="transparent decoding relay between the app and a real aGate")
    px.add_argument("target", help="real aGate, host or host:port (default port 9000)")
    px.add_argument("--listen", default="0.0.0.0:9000",
                    help="bind address host:port (default 0.0.0.0:9000)")
    px.add_argument("--once", action="store_true", help="serve a single connection then exit")
    px.add_argument("--record", metavar="FILE",
                    help="also write a pcap of the conversation (Wireshark-openable, "
                         "re-decodable with `franklinwh-direct-connect decode/analyze`)")
    px.set_defaults(func=_cmd_proxy)

    c = sub.add_parser("catalog", help="list known cmdType codes",
                       description="List the cmdType catalog. Every name listed is also "
                                   "a live subcommand.")
    c.add_argument("--json", action="store_true", help="emit JSON (machine-readable)")
    c.add_argument("--grep", metavar="TEXT",
                   help="filter by name, description, cloud equivalent, or code")
    c.set_defaults(func=_cmd_catalog)

    _SCAN_EXAMPLES = (
        "\nexamples:\n"
        "  # Quickest — auto-target the FranklinWH hotspot gateway (join AP_<serial> first):\n"
        "  franklinwh-direct-connect scan gateway\n\n"
        "  # Scan a whole subnet (your home LAN or the hotspot /24):\n"
        "  franklinwh-direct-connect scan 192.0.2.0/24\n"
        "  franklinwh-direct-connect scan 10.100.1.0/24\n\n"
        "  # Scan a specific host:\n"
        "  franklinwh-direct-connect scan 192.0.2.110\n\n"
        "  # Scan an IP range:\n"
        "  franklinwh-direct-connect scan 192.0.2.1-192.0.2.50\n\n"
        "  # Comma-separated mix:\n"
        "  franklinwh-direct-connect scan 192.0.2.110,10.100.1.1\n\n"
        "  # Larger subnet — reduce workers and increase timeout for reliability:\n"
        "  franklinwh-direct-connect scan 192.0.2.0/24 --timeout 1.0 --workers 32\n"
    )
    sc = sub.add_parser(
        "scan",
        help="scan LAN for FranklinWH gateways on TCP 9000 (sendMqtt) and 502 (Modbus)",
        description=(
            "Scan one or more hosts for the two ports used by FranklinWH aGate:\n"
            "  TCP 9000 — Direct-Connect broker (sendMqtt); also performs a login "
            "handshake to confirm the device and retrieve its serial number.\n"
            "  TCP 502  — Modbus TCP (local control).\n\n"
            "The aGate only listens on TCP 9000 when you are joined to its own WiFi "
            "hotspot (SSID AP_<serial>). On your home LAN it may listen on 502 only."
        ),
        epilog=_SCAN_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sc.add_argument(
        "targets",
        help=(
            "what to scan — one of:\n"
            "  gateway          auto-detect the FranklinWH hotspot gateway (join AP_<serial> first)\n"
            "  <IP>             single host, e.g. 192.0.2.110\n"
            "  <CIDR>           subnet, e.g. 192.0.2.0/24 or 10.100.1.0/24\n"
            "  <lo>-<hi>        IP range, e.g. 192.0.2.1-192.0.2.50\n"
            "  <a>,<b>,...      comma-separated mix of the above"
        ),
    )
    sc.add_argument(
        "--timeout", type=float, default=0.5,
        help="per-port connect timeout in seconds (default 0.5). "
             "Increase to 1.0–2.0 on slow or congested networks.",
    )
    sc.add_argument(
        "--workers", type=int, default=64,
        help="parallel scan threads (default 64). "
             "Lower to 16–32 if your OS limits open sockets.",
    )
    sc.add_argument(
        "--no-probe", action="store_true",
        help="open-port check only; skip the login/Modbus confirmation step "
             "(faster, but does not verify the device is a FranklinWH aGate).",
    )
    sc.add_argument("--json", action="store_true", help="emit results as JSON")
    sc.set_defaults(func=_cmd_scan)

    pb = sub.add_parser(
        "probe",
        help="live: sweep cmdType codes with a payload matrix to find new reads",
        description=(
            "Probe a live aGate for undocumented cmdTypes.\n\n"
            "For each code, several REQUEST payload shapes are tried — the plain\n"
            "{\"opt\":0} read, and per-battery selectors ({\"fhpSn\":SN,\"type\":2|3})\n"
            "matching how the cloud API's BMS read is addressed. A code that needs a\n"
            "selector answers a plain opt=0 probe with silence, so a single-shape sweep\n"
            "cannot find it.\n\n"
            "Read-only: no opt=1 write is ever sent. Known codes come from the catalog,\n"
            "so the swept set never goes stale.\n\n"
            "examples:\n"
            "  franklinwh-direct-connect -i 192.0.2.110 probe\n"
            "  franklinwh-direct-connect -i 192.0.2.110 probe --range 1413-1699\n"
            "  franklinwh-direct-connect -i 192.0.2.110 probe --codes 1207,1209,1821,1823,1825\n"
            "  franklinwh-direct-connect -i 192.0.2.110 probe --json > probe.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pb.add_argument("--range", dest="codes", metavar="LO-HI",
                    help="codes to sweep, e.g. 1413-1699 (alias of --codes)")
    pb.add_argument("--codes", dest="codes", metavar="SPEC",
                    help="explicit codes/ranges: '1207,1209' or '1413-1699'")
    pb.add_argument("--start", type=int, default=1101, help="sweep start (default 1101)")
    pb.add_argument("--end", type=int, default=1909, help="sweep end (default 1909)")
    pb.add_argument("--include-known", action="store_true",
                    help="also re-probe codes already in the catalog")
    pb.add_argument("--serial", action="append", metavar="SN",
                    help="fhpSn selector to try (repeatable; default: auto-discover)")
    pb.add_argument("--no-serials", action="store_true",
                    help="skip serial auto-discovery")
    pb.add_argument("--plain-only", action="store_true",
                    help="only send {\"opt\":0} (the old single-shape behaviour)")
    pb.add_argument("--payload", action="append", metavar="JSON",
                    help="custom request payload, repeatable; overrides the default "
                         "matrix. '%%fhpSn%%' expands to each battery serial, e.g. "
                         "--payload '{\"opt\":0,\"fhpSn\":\"%%fhpSn%%\"}'")
    pb.add_argument("--all-shapes", action="store_true",
                    help="try EVERY payload shape instead of stopping at the first "
                         "that responds, and keep the richest reply (use when a code "
                         "already answers opt=0 but looks thin)")
    pb.add_argument("--verbose", "-v", action="store_true",
                    help="also print timeouts and envelope-only replies")
    pb.add_argument("--json", action="store_true", help="emit JSON")
    pb.set_defaults(func=_cmd_probe)

    tou = sub.add_parser("tou", help="live: TOU tariff schedule as readable blocks",
                         description="Decode the gateway's TOU schedule (cmdType 1407) "
                                     "into ordered tariff blocks, with the gateway's own "
                                     "local time, timezone and DST flag.")
    tou.add_argument("--json", action="store_true", help="emit JSON")
    tou.add_argument("--bar", action="store_true",
                     help="draw a 24-column day bar beside each block")
    tou.set_defaults(func=_cmd_tou)

    er = sub.add_parser(
        "energy_rollup",
        help="live: week/month/year energy rollup, aggregated locally",
        description=(
            "Aggregate daily energy history (cmdType 1303) into a period total.\n\n"
            "The aGate serves ONE DAY per request and has no rollup call — the\n"
            "cloud's week/month/year figures are computed cloud-side. This does the\n"
            "same arithmetic locally, one request per day.\n\n"
            "Retention is a rolling ~105 days, so year/total come back PARTIAL; the\n"
            "result always reports its own coverage.\n\n"
            "examples:\n"
            "  franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period week\n"
            "  franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period month "
            "--date 2026-08-15\n"
            "  franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period total --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    er.add_argument("--period", choices=list(_energy.PERIODS), default="week",
                    help="rollup period (default week)")
    er.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="a date inside the period (default today)")
    er.add_argument("--stop-after-empty", type=int, default=5, metavar="N",
                    help="stop walking back after N consecutive empty days "
                         "(default 5; history is contiguous)")
    er.add_argument("--quiet", "-q", action="store_true",
                    help="no per-day progress marks")
    er.add_argument("--json", action="store_true", help="emit JSON")
    er.set_defaults(func=_cmd_energy_rollup)

    bt = sub.add_parser(
        "battery", aliases=["bms"],
        help="live: Battery Management view (per-cell telemetry, pack health, bus)",
        description=(
            "Per-cell BMS telemetry and pack health, read locally.\n\n"
            "Combines cmdTypes 1705 (cell voltages/temps, SoC/SoH), 1703 (grid and DC\n"
            "bus rails), 1835 (states) and 1833 (serials/firmware) in one session.\n\n"
            "Monitoring:\n"
            "  --watch [SECONDS]   refresh every SECONDS (default 5)\n"
            "  --for DURATION      stop after 90 / 30s / 5m / 2h\n"
            "  --count N           stop after N samples\n"
            "Ctrl-C stops at any time. On a terminal the view repaints in place; piped\n"
            "output appends, so a log keeps every sample.\n\n"
            "examples:\n"
            "  franklinwh-direct-connect -i 192.0.2.110 battery\n"
            "  franklinwh-direct-connect -i 192.0.2.110 battery --watch 2 --for 5m\n"
            "  franklinwh-direct-connect -i 192.0.2.110 battery --json > bms.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    bt.add_argument("--id", type=int, default=1, metavar="N",
                    help="aPower selector from device_check devMap[].id (default 1)")
    bt.add_argument("--watch", type=float, nargs="?", const=5.0, default=None,
                    metavar="SECONDS", help="refresh every SECONDS (default 5)")
    bt.add_argument("--for", dest="duration", metavar="DURATION",
                    help="stop after a duration: 90, 30s, 5m, 2h")
    bt.add_argument("--count", type=int, default=0, metavar="N",
                    help="stop after N samples")
    bt.add_argument("--no-colour", "--no-color", action="store_true",
                    help="plain text even on a terminal")
    bt.add_argument("--json", action="store_true", help="emit JSON per sample")
    bt.set_defaults(func=_cmd_battery)

    em = sub.add_parser("emulate", help="run a fake aGate broker for testing")
    em.add_argument("--bind", default="127.0.0.1",
                    help="host/IP to bind (default 127.0.0.1; use 0.0.0.0 in containers)")
    em.add_argument("--port", type=int, default=9000)
    em.add_argument("--seed", type=int, default=None,
                    help="enable the dynamic per-seed synthetic site (unique serial + "
                         "live-moving power/mode curve); omit for canned/pcap replies")
    em.add_argument("--serial", default=None,
                    help="override the emulated IBG_SN / equipNo")
    em.add_argument("--units", type=int, default=1,
                    help="number of aPowers to present (multi-battery mock)")
    em.add_argument("--static", action="store_true",
                    help="disable the dynamic site — answer only from canned/pcap data")
    em.set_defaults(func=_cmd_emulate)

    # -- live get-or-set control (need --host/-i), mirroring the cloud CLI --
    # 'mode_page' is the catalog's name for 1727; alias it so every catalog
    # name resolves to a command (see live_commands / DEF-CLI-CATALOG-DRIFT).
    md = sub.add_parser("mode", aliases=["mode_page"],
                        help="live: show current mode, or --set it")
    md.add_argument("--set", metavar="MODE",
                    help="set mode by id, full name, or alias (tou / self / backup)")
    md.add_argument("--list", action="store_true", help="list all modes + details")
    md.add_argument("--json", action="store_true", help="decoded dataArea as JSON")
    md.add_argument("--raw", action="store_true",
                    help="full on-the-wire frame (cmdType/equipNo/snno/crc/dataArea)")
    md.set_defaults(func=_cmd_control)

    gp = sub.add_parser("grid_profile",
                        help="live: full grid-compliance profile (fans out 25 cmdTypes)")
    gp.add_argument("--json", action="store_true", help="emit JSON (default)")
    gp.set_defaults(func=_cmd_grid_profile)

    og = sub.add_parser("offgrid", help="live: show off-grid status, or --set on/off")
    og.add_argument("--set", choices=["on", "off"], dest="set",
                    help="on = go off-grid, off = reconnect")
    og.add_argument("--soc", type=int, default=5, help="floor SoC%% while islanded")
    og.add_argument("--json", action="store_true", help="decoded dataArea as JSON")
    og.add_argument("--raw", action="store_true", help="full on-the-wire frame")
    og.set_defaults(func=_cmd_control)

    dc = sub.add_parser("der_comms",
                        help="live: show or set DER comms (SunSpec Modbus + IEEE 2030.5)")
    dc.add_argument("--set-modbus", choices=["on", "off"], dest="set_modbus",
                    help="enable/disable SunSpec Modbus (sunsMdEn). OFF stops :502 now; "
                         "ON needs a reboot to bind :502 (see --and-reboot)")
    dc.add_argument("--set-2030-5", choices=["on", "off"], dest="set_2030_5",
                    help="enable/disable IEEE 2030.5 / SEP2 (enabling hands dispatch to a "
                         "DERMS server; prompts to confirm)")
    dc.add_argument("--and-reboot", action="store_true",
                    help="with --set-modbus on: reboot after the write to bind :502, and "
                         "verify it comes back")
    dc.add_argument("--force", action="store_true",
                    help="skip the confirmation prompts")
    dc.add_argument("--json", action="store_true", help="decoded dataArea as JSON")
    dc.set_defaults(func=_cmd_der_comms)

    hc = sub.add_parser("health",
                        help="live: check aGate listeners (:9000/:502), login, Modbus config")
    hc.add_argument("--json", action="store_true", help="emit the checks as JSON")
    hc.set_defaults(func=_cmd_health)

    fw = sub.add_parser("firmware",
                        help="live: show the aGate firmware/version block (login manifest)")
    fw.add_argument("--json", action="store_true", help="emit the version block as JSON")
    fw.set_defaults(func=_cmd_firmware)

    rb = sub.add_parser("reboot",
                        help="live: reboot the aGate (asks to confirm; --force to skip)")
    rb.add_argument("--force", action="store_true",
                    help="skip the 'are you sure?' confirmation prompt")
    rb.add_argument("--wait", type=int, nargs="?", const=0, default=None, metavar="SECONDS",
                    help="poll until it reboots and returns (down->up + login); re-discovers "
                         "via scan if it lands on a new IP. SECONDS budget, or omit to wait "
                         "forever.")
    rb.set_defaults(func=_cmd_reboot)

    by_name = {i.name: i for i in catalog.CATALOG.values()}
    for name in live_commands():
        info = by_name.get(name)
        if info is None:
            blurb = "live: raw cmdType call"
        else:
            lead = "UNCONFIRMED — " if info.request in catalog.UNCONFIRMED else ""
            summary = info.description.split(":")[0].split(";")[0].strip()
            blurb = f"live [{info.request}]: {lead}{summary[:72]}"
        # argparse %-expands help strings; descriptions contain literal '%'.
        sp = sub.add_parser(name,
                            help=argparse.SUPPRESS if info is not None
                            else blurb.replace("%", "%%"),
                            description=blurb if info is None else
                            f"cmdType {info.request} -> {info.response}. {info.description}"
                            + (f"\n\nCloud equivalent: {info.cloud_api}" if info.cloud_api else ""),
                            formatter_class=argparse.RawDescriptionHelpFormatter)
        sp.set_defaults(catalog_cmd=None if info is None else info.request)
        if name == "call":
            sp.add_argument("cmd_type", type=int, nargs="?")
            sp.add_argument("--data", help="dataArea as JSON (default {\"opt\":0})")
        if info is not None and info.request in catalog.NEEDS_DATE:
            sp.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                            help="day to fetch (default today). The aGate keeps a "
                                 "rolling ~105-day window; older dates return sno=0")
        if info is not None and info.request in catalog.NEEDS_ID:
            sp.add_argument("--id", type=int, default=1, metavar="N",
                            help="device selector from device_check/battery_modules "
                                 "devMap[].id (default 1)")
        if name != "login":
            sp.add_argument("--watch", type=float, nargs="?", const=5.0, default=None,
                            metavar="SECONDS",
                            help="poll repeatedly every SECONDS (default 5) over one session")
            sp.add_argument("--count", type=int, default=0,
                            help="with --watch, stop after N samples (0 = forever)")
        sp.set_defaults(func=_cmd_live)

    return p


#: Commands that never open a connection — passing --host/-i to them is a no-op
#: and almost always means the user expected a live read.
OFFLINE_COMMANDS = frozenset({"catalog", "decode", "analyze", "emulate", "proxy"})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in OFFLINE_COMMANDS and getattr(args, "host", None):
        print(f"warning: '{args.command}' works offline — --host/-i "
              f"{args.host} is ignored.", file=sys.stderr)
    for attr, default in (("cmd_type", None), ("data", None), ("watch", None), ("count", 0),
                          ("soc", None), ("list", False), ("raw", False), ("id", 1),
                          ("date", None)):
        if not hasattr(args, attr):
            setattr(args, attr, default)
    if getattr(args, "date", None) is None:
        import datetime as _dt
        args.date = _dt.date.today().isoformat()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
