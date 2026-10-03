r"""
Wire protocol for the FranklinWH aGate local broker channel (TCP/9000).

Frame format
------------
A frame is a single JSON object. The header is sent in cleartext; everything
from the ``"type"`` field onward is obfuscated with a trivial position-based
additive cipher:

    {"cmdType":<N>,"equipNo":"<E>",   <-- cleartext header
    "type":<t>,"timeStamp":<ts>,"snno":<s>,"len":<L>,"crc":"<C>","dataArea":{...}}
    \-------------------- ciphered region (i = 0 at first byte) --------------------/

Cipher (symmetric, no key):
    encrypt: c[i] = (p[i] + seed + i) & 0xFF
    decrypt: p[i] = (c[i] - seed - i) & 0xFF

``seed`` is 0x3F for normal frames (20-char gateway serial) and 0xA5 for the
pre-login handshake (1101, which uses equipNo "00000000"). Because the first
plaintext byte is always a double-quote (0x22), decoding is *self-synchronizing*:
the seed is recovered from the first ciphered byte, so no seed needs to be known
in advance to read a frame.

Field rules (verified against captured traffic):
    len = byte length of the compact dataArea JSON string
    crc = CRC32 (zlib) of that same dataArea string, 8 uppercase hex digits

Set ``cipher=False`` to read/write the cleartext cloud-REST variant
(POST /hes-gateway/.../sendMqtt), which uses the same JSON without obfuscation.
"""

from __future__ import annotations

import json
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterator

from . import catalog

# The obfuscation seed is DERIVED FROM THE SERIAL (see derive_seed) — it is not a
# fixed constant. These two are kept for readability/back-compat: they are simply the
# derived seeds for the two serials we see most. derive_seed("00000000") == SEED_LOGIN
# and, for a 20-char reference serial, SEED_DEFAULT.
SEED_DEFAULT = 0x3F   # derive_seed(<reference 20-char serial>)
SEED_LOGIN = 0xA5     # derive_seed("00000000") — the 1101 login handshake
_FIRST_PLAINTEXT_BYTE = 0x22  # '"' — the byte that begins the ciphered region

_HEADER_RE = re.compile(rb'\{"cmdType":(\d+),"equipNo":"([0-9A-Za-z]*)",')


# ---------------------------------------------------------------------------
# Cipher
# ---------------------------------------------------------------------------
def encrypt_body(plain: bytes, seed: int = SEED_DEFAULT) -> bytes:
    return bytes((b + seed + i) & 0xFF for i, b in enumerate(plain))


def decrypt_body(cipher: bytes, seed: int) -> bytes:
    return bytes((b - seed - i) & 0xFF for i, b in enumerate(cipher))


def detect_seed(cipher: bytes) -> int:
    """Recover the seed from a ciphered region (plaintext[0] is always '"')."""
    if not cipher:
        return SEED_DEFAULT
    return (cipher[0] - _FIRST_PLAINTEXT_BYTE) & 0xFF


def derive_seed(equip_no: str) -> int:
    """Per-serial obfuscation seed: ``(sum(utf8(SN)) + len(SN) + 29) & 0xFF``.

    Formula recovered by voidstarr (https://github.com/voidstarr/franklinwh_local,
    MIT) from the FranklinWH Android app's Dart AOT, and independently confirmed here:
    it reproduces BOTH seeds we had only *observed* on the wire —
    ``derive_seed("00000000") == 0xA5`` (login) and, for our 20-char reference serial,
    ``0x3F``. Our previous code hardcoded ``0x3F`` for every non-login serial, so it
    silently mis-encoded every request sent to a gateway whose serial hashes to a
    different seed (i.e. anyone else's aGate). Decoding was unaffected — ``detect_seed``
    recovers the seed from the ciphertext — so this only bit the *send* path.
    """
    raw = (equip_no or "00000000").encode("utf-8")
    return (sum(raw) + len(raw) + 29) & 0xFF


def seed_for_equip(equip_no: str) -> int:
    """Seed to use when *encoding* a frame for the given equipNo."""
    return derive_seed(equip_no)


# ---------------------------------------------------------------------------
# dataArea len / crc helpers
# ---------------------------------------------------------------------------
def dataarea_str(data_area: Any) -> str:
    """Serialize dataArea exactly as the gateway does (compact, no spaces)."""
    if isinstance(data_area, str):
        return data_area
    return json.dumps(data_area, separators=(",", ":"))


def crc32_hex(s: str) -> str:
    return f"{zlib.crc32(s.encode('latin1')) & 0xFFFFFFFF:08X}"


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------
@dataclass
class Frame:
    cmd_type: int
    equip_no: str
    data_area: Any = field(default_factory=dict)
    type: int = 0
    time_stamp: int = 0
    snno: int = 0
    # populated on decode; recomputed on encode
    len: int | None = None
    crc: str | None = None
    seed: int | None = None
    raw_json: dict | None = None
    data_area_raw: str | None = None

    @property
    def name(self) -> str:
        return catalog.describe(self.cmd_type)

    @property
    def is_request(self) -> bool:
        return catalog.is_request(self.cmd_type)

    def verify(self) -> bool:
        """True if declared len/crc match the dataArea exactly as received."""
        s = self.data_area_raw if self.data_area_raw is not None else dataarea_str(self.data_area)
        ok = True
        if self.len is not None:
            ok &= self.len == len(s.encode("latin1"))
        if self.crc is not None:
            ok &= crc32_hex(s) == self.crc
        return ok

    def __repr__(self) -> str:
        d = "REQ" if self.is_request else "RSP"
        return f"<Frame {self.cmd_type} {d} {self.name!r} equip={self.equip_no}>"


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------
def encode_frame(
    cmd_type: int,
    equip_no: str,
    data_area: Any,
    *,
    type: int = 0,
    time_stamp: int = 0,
    snno: int = 0,
    seed: int | None = None,
    cipher: bool = True,
) -> bytes:
    """
    Build a complete on-the-wire frame.

    ``seed`` defaults to the value appropriate for ``equip_no``. Pass
    ``cipher=False`` for the cleartext cloud-REST body.
    """
    da = dataarea_str(data_area)
    length = len(da.encode("latin1"))
    crc = crc32_hex(da)
    header = f'{{"cmdType":{cmd_type},"equipNo":"{equip_no}",'
    rest = (
        f'"type":{type},"timeStamp":{time_stamp},"snno":{snno},'
        f'"len":{length},"crc":"{crc}","dataArea":{da}}}'
    )
    if not cipher:
        return (header + rest).encode("latin1")
    if seed is None:
        seed = seed_for_equip(equip_no)
    return header.encode("latin1") + encrypt_body(rest.encode("latin1"), seed)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------
def decode_frame(raw: bytes, *, cipher: bool = True, seed: int | None = None) -> Frame:
    """Parse one complete frame (cleartext header + (ciphered) remainder)."""
    m = _HEADER_RE.match(raw)
    if not m:
        raise ValueError("not a sendMqtt frame (header not found)")
    header = raw[: m.end()]
    body = raw[m.end():]
    used_seed = None
    if cipher:
        used_seed = detect_seed(body) if seed is None else seed
        plain = decrypt_body(body, used_seed)
    else:
        plain = body
    text = (header + plain).decode("latin1")
    obj = json.loads(text)
    return Frame(
        cmd_type=int(m.group(1)),
        equip_no=m.group(2).decode(),
        data_area=obj.get("dataArea", {}),
        type=obj.get("type", 0),
        time_stamp=obj.get("timeStamp", 0),
        snno=obj.get("snno", 0),
        len=obj.get("len"),
        crc=obj.get("crc"),
        seed=used_seed,
        raw_json=obj,
        data_area_raw=_extract_dataarea_raw(text),
    )


def _extract_dataarea_raw(text: str) -> str | None:
    k = text.find('"dataArea":')
    if k < 0:
        return None
    s = text[k + len('"dataArea":'):].rstrip()
    if s.endswith("}"):
        s = s[:-1]
    return s.strip()


def _balanced_json_end(text: str) -> int | None:
    """Index just past the first balanced top-level {...}, else None."""
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


# ---------------------------------------------------------------------------
# Streaming reader (TCP segmentation / multiple frames per read)
# ---------------------------------------------------------------------------
class FrameStream:
    """
    Feed raw bytes from one direction of a TCP connection; pull complete Frames.

    Handles frames split across reads and several frames per read. The seed is
    detected per frame, so logins and normal frames decode transparently.
    """

    def __init__(self, cipher: bool = True):
        self._buf = bytearray()
        self._cipher = cipher

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        out: list[Frame] = []
        while True:
            frame, consumed = self._try_one()
            if frame is None:
                break
            out.append(frame)
            del self._buf[:consumed]
        return out

    def _try_one(self) -> tuple[Frame | None, int]:
        m = _HEADER_RE.match(self._buf)
        if not m:
            nxt = self._buf.find(b'{"cmdType":', 1)
            if nxt > 0:
                del self._buf[:nxt]
            return None, 0
        header_end = m.end()
        region = bytes(self._buf[header_end:])
        seed = detect_seed(region) if self._cipher else None
        plain = decrypt_body(region, seed) if self._cipher else region
        text = self._buf[:header_end].decode("latin1") + plain.decode("latin1")
        end = _balanced_json_end(text)
        if end is None:
            return None, 0  # need more bytes
        try:
            obj = json.loads(text[:end])
        except json.JSONDecodeError:
            nxt = self._buf.find(b'{"cmdType":', 1)
            if nxt > 0:
                del self._buf[:nxt]
            else:
                self._buf.clear()
            return None, 0
        frame = Frame(
            cmd_type=int(m.group(1)), equip_no=m.group(2).decode(),
            data_area=obj.get("dataArea", {}), type=obj.get("type", 0),
            time_stamp=obj.get("timeStamp", 0), snno=obj.get("snno", 0),
            len=obj.get("len"), crc=obj.get("crc"), seed=seed,
            raw_json=obj, data_area_raw=_extract_dataarea_raw(text[:end]),
        )
        return frame, end


# ---------------------------------------------------------------------------
# pcap reader (classic format, Ethernet/IPv4/TCP) with TCP reassembly
# ---------------------------------------------------------------------------
def iter_pcap_frames(path: str, port: int = 9000, cipher: bool = True) -> Iterator[Frame]:
    """Yield decoded Frames from a classic-format pcap, with TCP reassembly."""
    data = open(path, "rb").read()
    magic = data[:4]
    if magic not in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
        raise ValueError("not a classic pcap")
    en = "<" if magic == b"\xd4\xc3\xb2\xa1" else ">"

    streams: dict[tuple, list[tuple[int, bytes]]] = {}
    off = 24
    while off + 16 <= len(data):
        _, _, incl, _ = struct.unpack(en + "IIII", data[off:off + 16])
        off += 16
        raw = data[off:off + incl]
        off += incl
        if len(raw) < 14 or struct.unpack(">H", raw[12:14])[0] != 0x0800:
            continue
        ip = raw[14:]
        ihl = (ip[0] & 0x0F) * 4
        if ip[9] != 6:
            continue
        iplen = struct.unpack(">H", ip[2:4])[0]
        tcp = ip[ihl:]
        sport, dport = struct.unpack(">HH", tcp[0:4])
        if port not in (sport, dport):
            continue
        seq = struct.unpack(">I", tcp[4:8])[0]
        doff = (tcp[12] >> 4) * 4
        payload = tcp[doff: iplen - ihl]
        if not payload:
            continue
        key = (bytes(ip[12:16]), sport, bytes(ip[16:20]), dport)
        streams.setdefault(key, []).append((seq, payload))

    for segs in streams.values():
        base = min(s for s, _ in segs)
        buf = bytearray()
        for seq, pl in sorted(segs, key=lambda x: x[0]):
            pos = seq - base
            if pos < 0:
                continue
            if pos + len(pl) > len(buf):
                buf.extend(b"\x00" * (pos + len(pl) - len(buf)))
            buf[pos:pos + len(pl)] = pl
        yield from FrameStream(cipher=cipher).feed(bytes(buf))
