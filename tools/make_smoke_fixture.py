#!/usr/bin/env python3
"""Generate tests/fixtures/smoke.pcap — a synthetic capture for the CI smoke test.

The smoke step used to decode `tests/fixtures/fhp_wifi_ap.pcap`, a real capture that
was stripped when this repo went public. Nothing replaced it, so `smoke` has failed
since. A real capture cannot be committed (it carries a gateway serial and session
data), so this builds an equivalent from the library's own encoder and pcap writer:
synthetic frames, RFC 5737 addresses, no device data. Deterministic.

Regenerate:  python tools/make_smoke_fixture.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from franklinwh_direct_connect_api import encode_frame, iter_pcap_frames  # noqa: E402
from franklinwh_direct_connect_api import proxy as proxy_mod  # noqa: E402
from franklinwh_direct_connect_api.proxy import APP_TO_AGATE, AGATE_TO_APP, PcapWriter  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures/smoke.pcap"
GATEWAY = "FAKEGATE90FJ09J6H4F2"      # not a real serial

# One request/response pair per exchange: a power-flow read and a mode read.
EXCHANGES = [
    (1301, {"opt": 0}, 1302, {"opt": 0, "result": 0, "soc": 50.0, "p_sun": 1234}),
    (1725, {"opt": 0}, 1726, {"opt": 0, "result": 0, "current_id": 85232}),
]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # PcapWriter stamps each packet with time.time(). Freeze it so regenerating the
    # fixture is byte-identical and never shows up as a spurious diff.
    proxy_mod.time.time = lambda: 1_700_000_000.0
    rec = PcapWriter(str(OUT))
    try:
        for req_cmd, req, resp_cmd, resp in EXCHANGES:
            rec.write(APP_TO_AGATE, encode_frame(req_cmd, GATEWAY, req))
            rec.write(AGATE_TO_APP, encode_frame(resp_cmd, GATEWAY, resp))
    finally:
        rec.close()

    frames = list(iter_pcap_frames(str(OUT)))
    # iter_pcap_frames reassembles each TCP direction as its own stream, so frames
    # arrive grouped by direction (all requests, then all responses) rather than
    # interleaved as they were written. Compare as a multiset.
    want = sorted(c for ex in EXCHANGES for c in (ex[0], ex[2]))
    got = sorted(f.cmd_type for f in frames)
    if got != want:
        print(f"FAIL: decoded {got}, expected {want}", file=sys.stderr)
        return 1
    print(f"wrote {OUT.relative_to(OUT.parents[1])} — {OUT.stat().st_size} bytes, "
          f"{len(frames)} frames: {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
