"""Transparent proxy relay + decode, end-to-end against a synthetic emulator.

No capture file: a client drives the in-process emulator through the decoding proxy,
and we assert both directions decode. (The offline ``analyze`` CLI still operates on any
capture a user supplies; there is nothing bundled to test it against.)
"""

from __future__ import annotations

import threading
import time

import pytest

from franklinwh_direct_connect_api import proxy
from franklinwh_direct_connect_api.client import LocalClient
from franklinwh_direct_connect_api.emulator import Emulator


@pytest.fixture
def emulator():
    emu = Emulator("127.0.0.1", 0).start()
    yield emu
    emu.stop()


def test_proxy_relays_and_decodes(emulator):
    seen: list[tuple[str, int]] = []
    port_ready: list[int] = []
    ready = threading.Event()

    def on_listen(port):
        port_ready.append(port)
        ready.set()

    def on_frame(direction, frame):
        seen.append((direction, frame.cmd_type))

    t = threading.Thread(
        target=proxy.serve,
        args=("127.0.0.1", 0, "127.0.0.1", emulator.port),
        kwargs={"on_frame": on_frame, "once": True, "on_listen": on_listen},
        daemon=True,
    )
    t.start()
    assert ready.wait(3.0), "proxy never bound"
    proxy_port = port_ready[0]

    # Drive a real client THROUGH the proxy.
    with LocalClient("127.0.0.1", proxy_port, timeout=3.0) as c:
        manifest = c.login()
        assert manifest["IBG_SN"] == emulator.equip_no   # the emulator's own (synthetic) serial
        flow = c.power_flow()
        assert "soc" in flow

    time.sleep(0.2)  # let the pump drain
    dirs = {d for d, _ in seen}
    cmds = {cmd for _, cmd in seen}
    # Both directions decoded, login + power_flow frames observed end-to-end.
    assert proxy.APP_TO_AGATE in dirs and proxy.AGATE_TO_APP in dirs
    assert 1101 in cmds and 1102 in cmds  # login request + reply
    assert 1301 in cmds or 1302 in cmds   # power flow


def test_proxy_record_writes_decodable_pcap(emulator, tmp_path):
    """--record writes a pcap that re-decodes cleanly (recreate captures on demand)."""
    from franklinwh_direct_connect_api.protocol import iter_pcap_frames

    pcap = tmp_path / "rec.pcap"
    port_ready: list[int] = []
    ready = threading.Event()

    def on_listen(port):
        port_ready.append(port)
        ready.set()

    t = threading.Thread(
        target=proxy.serve,
        args=("127.0.0.1", 0, "127.0.0.1", emulator.port),
        kwargs={"once": True, "on_listen": on_listen, "record": str(pcap)},
        daemon=True,
    )
    t.start()
    assert ready.wait(3.0), "proxy never bound"

    with LocalClient("127.0.0.1", port_ready[0], timeout=3.0) as c:
        c.login()
        assert "soc" in c.power_flow()
    t.join(3.0)  # proxy finishes the connection and closes the writer

    frames = list(iter_pcap_frames(str(pcap)))   # default port 9000 — canonical
    assert frames and all(f.verify() for f in frames)
    cmds = {f.cmd_type for f in frames}
    assert 1101 in cmds and 1102 in cmds and (1301 in cmds or 1302 in cmds)


def test_proxy_keeps_the_reserved_port_and_the_reason_is_recorded():
    """`proxy` is the documented exception to the TCP 9000 reserved-port rule.

    Owner's ruling, 2026-10-31, asked and answered more than once. The rule is about
    what is behind the socket, not the number: the emulator is refused on 9000
    because it answers with SYNTHETIC data, while the proxy relays every byte to a
    REAL aGate and never answers on its own behalf.

    This test exists so nobody "consistently" applies the emulator's refusal here and
    silently breaks app capture, which is the one workflow that needs :9000.
    """
    from pathlib import Path

    from franklinwh_direct_connect_api import cli, proxy

    listen = next(a for a in cli.build_parser()._subparsers._group_actions[0]
                  .choices["proxy"]._actions if a.dest == "listen")
    assert listen.default == "0.0.0.0:9000", "the proxy's listen default must stay :9000"

    # And the reason is written down next to the code, not only in a commit message.
    doc = Path(proxy.__file__).read_text()
    assert "Listening on TCP 9000" in doc
    assert "never answers on its own behalf" in doc
