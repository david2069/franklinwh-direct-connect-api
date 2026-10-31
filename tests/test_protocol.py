"""Protocol-level tests — in-memory frames, no captures."""

from __future__ import annotations


import pytest

from franklinwh_direct_connect_api import protocol
from franklinwh_direct_connect_api.protocol import (
    crc32_hex,
    dataarea_str,
    decode_frame,
    encode_frame,
)

EQUIP = "FAKEGATE90FJ09J6H4F2"


# -- cipher ------------------------------------------------------------------
def test_cipher_roundtrip():
    for seed in (protocol.SEED_DEFAULT, protocol.SEED_LOGIN, 0, 255):
        data = bytes(range(256))
        assert protocol.decrypt_body(protocol.encrypt_body(data, seed), seed) == data


def test_detect_seed_matches_known():
    # plaintext '"type"...' -> first ciphered byte encodes seed
    body = protocol.encrypt_body(b'"type":0', protocol.SEED_DEFAULT)
    assert protocol.detect_seed(body) == protocol.SEED_DEFAULT
    body = protocol.encrypt_body(b'"type":0', protocol.SEED_LOGIN)
    assert protocol.detect_seed(body) == protocol.SEED_LOGIN


def test_seed_for_equip():
    assert protocol.seed_for_equip("00000000") == protocol.SEED_LOGIN
    assert protocol.seed_for_equip(EQUIP) == protocol.SEED_DEFAULT


# -- encode/decode -----------------------------------------------------------
def test_encode_decode_roundtrip():
    wire = encode_frame(1301, EQUIP, {"opt": 0}, time_stamp=1742739351, snno=4)
    fr = decode_frame(wire)
    assert fr.cmd_type == 1301 and fr.data_area == {"opt": 0}
    assert fr.len == 9 and fr.crc == crc32_hex('{"opt":0}')
    assert fr.verify()


def test_len_and_crc_rule():
    da = {"optType": 0, "paraType": 6}
    wire = encode_frame(1117, EQUIP, da)
    fr = decode_frame(wire)
    assert fr.len == len(dataarea_str(da).encode())
    assert fr.crc == crc32_hex(dataarea_str(da))


def test_cleartext_cloud_variant_matches_har():
    # Known cloud-REST frame from HTTPToolkit capture.
    body = encode_frame(327, EQUIP, {"opt": 0}, time_stamp=1773997097, cipher=False)
    assert b'"crc":"871767CE"' in body
    assert b'"len":9' in body


def test_login_frame_uses_login_seed():
    wire = encode_frame(1101, "00000000", {"opt": 0, "minProtocolVer": "V1.00.00"})
    fr = decode_frame(wire)  # seed auto-detected
    assert fr.cmd_type == 1101
    assert fr.seed == protocol.SEED_LOGIN
    assert fr.data_area["minProtocolVer"] == "V1.00.00"


# -- against the real capture ------------------------------------------------


# -- run_status enum (aligns with the cloud API's RUN_STATUS) -----------------
def test_run_status_desc_known_and_unknown():
    from franklinwh_direct_connect_api import RUN_STATUS, run_status_desc

    assert run_status_desc(0) == "Standby"
    assert run_status_desc(1) == "Charging"
    assert run_status_desc(2) == "Discharging"
    assert run_status_desc(9) == "VPP mode"
    # parity with the cloud enum keys
    assert {0, 1, 2, 5, 6, 7, 8, 9} <= set(RUN_STATUS)
    # unknown codes fall through, never raise
    assert "unknown" in run_status_desc(99)


# -- newly cataloged read codes + confirmed control writes (2026-06-19) -------
def test_new_read_codes_cataloged():
    from franklinwh_direct_connect_api import catalog
    assert catalog.response_for(1411) == 1412   # smart-circuit meter
    assert catalog.response_for(1901) == 1902    # generator + charge schedule
    assert "smart_circuit_meter" in catalog.describe(1411)
    assert "generator" in catalog.describe(1901)


def test_swept_cmdtypes_cataloged():
    # cmdTypes confirmed by the 2026-07 live sweep (corrected frame matching).
    from franklinwh_direct_connect_api import catalog
    for cmd, needle in [(1205, "der_comms"), (1401, "smart_circuit_schedule"),
                        (1721, "device_control")]:
        assert catalog.response_for(cmd) == cmd + 1
        assert needle in catalog.describe(cmd)
    # SunSpec Modbus toggle documented on 1205
    assert "SunSpec" in catalog.CATALOG[1205].description
    # minimal/unconfirmed cmdTypes are present but honestly flagged
    for cmd in (1207, 1209, 1823, 1825):
        assert "UNCONFIRMED" in catalog.CATALOG[cmd].description
    # 1821 left that set on 2026-10-23: it is the installer app's Debug Mode enable,
    # written from code and read back on the reference aGate. Its entry must carry the
    # safety consequence, because turning it on stops the battery.
    dm = catalog.CATALOG[1821]
    assert dm.name == "debug_mode"
    assert "UNCONFIRMED" not in dm.description
    assert "STOPS NORMAL BATTERY OPERATION" in dm.description


def test_response_for_unknown_odd_uses_convention():
    # Un-catalogued ODD requests fall back to response = request + 1 so probing works.
    from franklinwh_direct_connect_api import catalog
    assert 4137 not in catalog.CATALOG
    assert catalog.response_for(4137) == 4138   # odd -> +1
    assert catalog.response_for(4138) is None    # even (non-request) -> None


def test_writes_reference():
    from franklinwh_direct_connect_api import WRITES, catalog
    assert WRITES["set_mode"] == {"cmd": 1727, "opt": 3, "fields": ["current_id"],
                                  "note": WRITES["set_mode"]["note"]}
    # every write targets a cataloged request cmdType
    for w in WRITES.values():
        assert w["cmd"] in catalog.CATALOG
        assert w["opt"] in (1, 3)


def test_operating_modes_enum_mapping():
    """modbus oldIndex and cloud workMode swap TOU & Backup; only Self matches."""
    from franklinwh_direct_connect_api import OPERATING_MODES as M
    assert M["Emergency Backup"] == {"modbus": 1, "cloud": 3}
    assert M["Self-Consumption"] == {"modbus": 2, "cloud": 2}
    assert M["Time-of-Use"] == {"modbus": 3, "cloud": 1}
    # the swap that bites: modbus != cloud for TOU and Backup
    assert M["Time-of-Use"]["modbus"] != M["Time-of-Use"]["cloud"]


def test_mode_label_overrides_site_tariff_name():
    """TOU's site-specific tariff name -> canonical 'Time-of-Use' (app/FWHAI)."""
    from franklinwh_direct_connect_api import mode_label
    assert mode_label({"scheduling_type": 1, "name": "Ausgrid EA11 TOU"}) == "Time-of-Use"
    assert mode_label({"scheduling_type": 2, "name": "Self-Consumption"}) == "Self-Consumption"
    assert mode_label({"scheduling_type": 3, "name": "Emergency Backup"}) == "Emergency Backup"
    assert mode_label({"name": "Mystery"}) == "Mystery"  # unknown -> raw fallback


def test_derive_seed_matches_known_wire_seeds():
    # The formula reproduces BOTH seeds we had only observed on the wire.
    assert protocol.derive_seed("00000000") == protocol.SEED_LOGIN   # 0xA5 login
    assert protocol.derive_seed(EQUIP) == protocol.SEED_DEFAULT       # 0x3F reference serial


def test_derive_seed_is_per_serial_not_hardcoded():
    # The old bug: every non-login serial got 0x3F. Different serials must differ,
    # else we'd silently mis-encode requests to other gateways.
    others = {
        "10060006A00X00000001": 0x38,  # pii: allow — documentation placeholder
        "10050013A00X00000002": 0x36,  # pii: allow — documentation placeholder
        "FAKEAPOWERP6KMFY7ALA": 0xD8,
    }
    for sn, expected in others.items():
        assert protocol.derive_seed(sn) == expected
        assert protocol.derive_seed(sn) != protocol.SEED_DEFAULT      # not the old hardcode
        assert protocol.seed_for_equip(sn) == expected                # encode path uses it


def test_frame_roundtrips_for_a_foreign_serial():
    # A frame built for someone else's gateway must encode with that serial's seed and
    # decode back cleanly (detect_seed recovers it) — proving multi-gateway send works.
    sn = "10060006A00X00000001"  # pii: allow — documentation placeholder
    wire = protocol.encode_frame(1301, sn, {"opt": 0}, snno=7)
    fr = protocol.decode_frame(wire)
    assert fr.equip_no == sn
    assert fr.seed == protocol.derive_seed(sn)
    assert fr.data_area == {"opt": 0}
    assert fr.verify()


# -- a damaged stream must not silently discard everything after the damage ---
def _three_frames() -> bytes:
    from franklinwh_direct_connect_api.protocol import encode_frame
    return b"".join(
        encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0, "n": i},
                     time_stamp=1700000000 + i, snno=i)
        for i in range(3)
    )


def test_feed_resynchronises_past_garbage_instead_of_stopping():
    """One unparseable region used to discard the whole rest of the stream.

    `_try_one` returned (None, 0) for BOTH "need more bytes" and "skipped
    garbage", and `feed` broke on either. A real 1508-packet capture decoded as
    12 frames with no error; resynchronising recovered 335.
    """
    from franklinwh_direct_connect_api.protocol import FrameStream

    blob = _three_frames()
    damaged = blob[:len(blob) // 3] + b"\x00" * 64 + blob[len(blob) // 3:]

    # feed() ALONE must get past the damage. Calling flush() here too would mask
    # the fix -- flush recovers it either way, which is how a first version of
    # this test passed with the change reverted and proved nothing.
    fs = FrameStream()
    frames = fs.feed(damaged)
    assert len(frames) >= 2, (
        f"feed() stopped at the damage and recovered only {len(frames)} frames; "
        "it must resynchronise and continue")
    assert fs.skipped_bytes > 0, "damage was not reported as skipped bytes"


def test_flush_recovers_a_frame_that_feed_must_wait_on():
    """`feed` waits on an incomplete frame; `flush` says no more bytes are coming.

    That distinction is the whole fix: waiting is right for a socket and fatal
    for a file.
    """
    from franklinwh_direct_connect_api.protocol import FrameStream

    blob = _three_frames()
    truncated = blob[:-20]                      # last frame cut short

    fs = FrameStream()
    during = fs.feed(truncated)
    after = fs.flush()
    assert len(during) >= 2
    assert len(during) + len(after) >= 2
    assert not fs._buf, "flush must leave nothing buffered"


def test_feed_still_waits_for_an_incomplete_frame_on_a_live_stream():
    """The streaming path must NOT resync eagerly -- a split frame is normal.

    If feed() discarded a partial frame, every frame split across two TCP reads
    would be lost on a live socket. Verified by splitting mid-frame.
    """
    from franklinwh_direct_connect_api.protocol import FrameStream

    blob = _three_frames()
    cut = len(blob) - 10
    fs = FrameStream()
    first = fs.feed(blob[:cut])
    second = fs.feed(blob[cut:])
    assert len(first) + len(second) == 3, "a split frame was lost"
    assert fs.skipped_bytes == 0, "a clean split must not count as damage"


def test_a_clean_stream_reports_no_skipped_bytes():
    from franklinwh_direct_connect_api.protocol import FrameStream

    fs = FrameStream()
    frames = fs.feed(_three_frames()) + fs.flush()
    assert len(frames) == 3
    assert fs.skipped_bytes == 0
