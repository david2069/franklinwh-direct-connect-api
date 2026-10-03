"""
franklinwh-local
================
Unofficial Python library for the FranklinWH aGate **local broker protocol**
(the JSON ``cmdType`` frames seen on TCP/9000), the lower-level channel that the
cloud ``sendMqtt`` REST relay sits on top of.

Quick start
-----------
Decode a capture::

    from franklinwh_local import iter_pcap_frames
    for frame in iter_pcap_frames("capture.pcap"):
        print(frame, frame.data_area)

Build/parse a single frame::

    from franklinwh_local import encode_frame, decode_frame
    wire = encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0})
    frame = decode_frame(wire)

Talk to a gateway (live)::

    from franklinwh_local import LocalClient
    with LocalClient("10.100.1.1") as c:
        c.login()
        print(c.power_flow())
"""

from .catalog import (
    CATALOG,
    OPERATING_MODES,
    RUN_STATUS,
    WORK_MODE_NAMES,
    WRITES,
    Cmd,
    CmdInfo,
    describe,
    mode_label,
    response_for,
    run_status_desc,
)
from .client import LocalClient
from .protocol import (
    Frame,
    FrameStream,
    decode_frame,
    derive_seed,
    detect_seed,
    encode_frame,
    iter_pcap_frames,
)
from .transport import LocalTransport, TransportError
from .discover import HostResult, expand_targets, scan
from .emulator import Emulator
from .proxy import log_frame, serve as proxy_serve

__version__ = "0.3.0"

__all__ = [
    "Cmd",
    "CmdInfo",
    "CATALOG",
    "OPERATING_MODES",
    "RUN_STATUS",
    "WORK_MODE_NAMES",
    "WRITES",
    "describe",
    "mode_label",
    "response_for",
    "run_status_desc",
    "Frame",
    "FrameStream",
    "encode_frame",
    "decode_frame",
    "derive_seed",
    "detect_seed",
    "iter_pcap_frames",
    "LocalTransport",
    "TransportError",
    "LocalClient",
    "Emulator",
    "HostResult",
    "scan",
    "expand_targets",
    "proxy_serve",
    "log_frame",
    "__version__",
]
