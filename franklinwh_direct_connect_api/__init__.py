"""
franklinwh-direct-connect-api
============================
Unofficial Python library for the FranklinWH aGate **local broker protocol**
(the JSON ``cmdType`` frames seen on TCP/9000), the lower-level channel that the
cloud ``sendMqtt`` REST relay sits on top of.

Quick start
-----------
Decode a capture::

    from franklinwh_direct_connect_api import iter_pcap_frames
    for frame in iter_pcap_frames("capture.pcap"):
        print(frame, frame.data_area)

Build/parse a single frame::

    from franklinwh_direct_connect_api import encode_frame, decode_frame
    wire = encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0})
    frame = decode_frame(wire)

Talk to a gateway (live)::

    from franklinwh_direct_connect_api import DirectConnectClient
    with DirectConnectClient("10.100.1.1") as c:
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
from .client import DirectConnectClient
from .protocol import (
    Frame,
    FrameStream,
    decode_frame,
    derive_seed,
    detect_seed,
    encode_frame,
    iter_pcap_frames,
)
from .transport import DirectConnectTransport, TransportError
from .discover import HostResult, expand_targets, scan
from .emulator import Emulator
from .proxy import log_frame, serve as proxy_serve

__version__ = "0.4.0"

#: ``LocalClient``/``LocalTransport`` predate the rename to "Direct Connect"
#: (FranklinWH's own term for this protocol) and remain as aliases of the
#: canonical classes — same objects, so ``isinstance`` and subclassing are
#: unaffected. Removal in 0.5.0, with the ``franklinwh_local`` alias package.
LocalClient = DirectConnectClient
LocalTransport = DirectConnectTransport

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
    "DirectConnectTransport",
    "DirectConnectClient",
    "LocalTransport",      # deprecated alias of DirectConnectTransport
    "LocalClient",         # deprecated alias of DirectConnectClient
    "TransportError",
    "Emulator",
    "HostResult",
    "scan",
    "expand_targets",
    "proxy_serve",
    "log_frame",
    "__version__",
]
