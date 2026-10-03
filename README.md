# franklinwh-local

Unofficial Python library and CLI for the **FranklinWH aGate local broker protocol** —
the JSON `cmdType` frames exchanged over **TCP/9000**, the local interface the official
FranklinWH app calls **"Direct Connect."** This is the lower-level device↔broker channel
that the cloud `sendMqtt` REST relay (see
[`franklinwh-cloud`](https://github.com/david2069/franklinwh-cloud)) is layered on top of.

> **Status: alpha.** The protocol was reverse-engineered from packet captures.
> Frame parsing/encoding and the offline tooling are well tested; live transport
> against real hardware should be validated on your own LAN.

## Why this exists

A FranklinWH aGate can be reached three different ways:

- **The FranklinWH Cloud API** — what the official **mobile app** and the **FleetView**
  installer portal use. Capable, but it routes through FranklinWH's servers and needs an
  account and an internet connection.
- **Modbus TCP (SunSpec)** — a standards-based local interface. Good for basic power/energy
  reads and a few setpoints, but only a narrow slice of what the device actually knows.
- **The aGate's own local broker protocol** — the proprietary `sendMqtt` `cmdType` channel
  on **TCP/9000** that the app itself speaks under the hood. The official FranklinWH app
  calls this interface **"Direct Connect."** This is what `franklinwh-local` implements.

The project exists to demonstrate that third path: a fully **local, no-cloud, no-account**
way to **query, control, and administer** an aGate directly on your LAN — no FranklinWH
servers, no Modbus gateway required. Because it's the device's *native* channel, it surfaces
the deep structural telemetry the cloud strips out to keep the app fast (per-cell battery
voltages, relay/contactor states, full physics arrays), plus configuration and control
(operating mode, off-grid, reboot) — things neither a plain Modbus read nor the cloud expose
together in one place.

> **On the name "Direct Connect":** the official FranklinWH app uses this label for the local
> interface; this project adopts the term **purely to identify the same channel**. It implies
> **no affiliation with, endorsement by, or support from FranklinWH** — this is unofficial,
> reverse-engineered software, provided as-is.

**Docs:** [USAGE.md](docs/USAGE.md) (full how-to) · [PROTOCOL.md](docs/PROTOCOL.md) (wire format + command catalog) · [API.md](docs/API.md) (API reference)

A rendered docs site (MkDocs Material) is published from `docs/` via GitHub
Actions. Build it locally with:

```bash
pip install -e ".[docs]"
mkdocs serve        # http://127.0.0.1:8000
```

## Setup

Requires **Python 3.10+**. No runtime dependencies (standard library only).

```bash
git clone https://github.com/david2069/franklinwh-local
cd franklinwh-local

python3 -m venv .venv          # 1. create a virtualenv
source .venv/bin/activate      # 2. activate it  (Windows: .venv\Scripts\activate)
pip install -e .               # 3. install this checkout (editable)

franklinwh-local --version     # 4. verify
# franklinwh-local 0.1.0
```

Add `".[test]"` instead of `"."` in step 3 if you want to run the pytest suite.
From PyPI (no checkout needed) the install is `pip install franklinwh-direct-connect-api`.

### How to run it

`franklinwh-local` is a **console script** that `pip install` puts on your
`PATH` — it is *not* a `.py` file in this repo, so these do **not** work:

```bash
python franklinwh-local ...        # can't open file '.../franklinwh-local'
python franklinwh_local.py ...     # no such file
```

Run it one of these three ways:

```bash
franklinwh-local catalog                    # venv activated (recommended)
.venv/bin/franklinwh-local catalog          # venv not activated — call it by path
python -m franklinwh_local catalog          # module form; works anywhere the package imports
```

The names are easy to mix up: the PyPI distribution is
**`franklinwh-direct-connect-api`**, the import package is **`franklinwh_local`**
(underscore), and the CLI command is **`franklinwh-local`** (hyphen).

Everything below assumes the venv is activated. Offline commands
(`catalog`, `decode`, `analyze`, `emulate`) need no hardware — start with
`franklinwh-local catalog` to confirm your install works.

### Troubleshooting the install

| Symptom | Cause / fix |
| --- | --- |
| `can't open file '.../franklinwh-local'` | You ran `python franklinwh-local`. Drop the `python` — it's a command, not a script. |
| `command not found: franklinwh-local` | The venv isn't activated (`source .venv/bin/activate`), or `pip install -e .` hasn't been run in it. |
| `No module named franklinwh_local` | You're on a different interpreter than the one you installed into. Check with `which python` and `pip -V` — both should point inside `.venv`. |
| `error: externally-managed-environment` | You ran `pip install` outside a venv on a Homebrew/system Python. Create and activate the venv first. |

## Quick start

Decode a capture (offline, no hardware):

```python
from franklinwh_local import iter_pcap_frames

for frame in iter_pcap_frames("capture.pcap"):
    print(frame, frame.data_area)
```

Build and parse a single frame:

```python
from franklinwh_local import encode_frame, decode_frame

wire  = encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0})  # power-flow poll
frame = decode_frame(wire)
assert frame.verify()          # len + crc check
```

Talk to a live gateway:

```python
from franklinwh_local import LocalClient

with LocalClient("10.100.1.1") as c:   # the hotspot gateway IP
    c.login()                  # 1101 -> 1102 (firmware manifest)
    print(c.power_flow()["soc"])
    print(c.smart_circuits())

    bms = c.battery_cells(1)   # per-cell telemetry, the deep read
    print(bms["batVolt"])      # [3326, 3326, ...] mV per cell
    print(bms["batTemp"])      # [18.8, 18.9, ...] degC per cell
    print(bms["batSoh"])       # 94.9
```

### Battery Management

```bash
franklinwh-local -i 192.0.2.110 battery            # per-cell view
franklinwh-local -i 192.0.2.110 battery --watch 2 --for 10m
```

Per-cell voltages and temperatures, pack SoC/SoH, bus rails and states — one session,
local only. `--watch`/`--for`/`--count` monitor continuously; Ctrl-C stops.

### Per-device reads

Four reads are addressed to a **specific device** rather than the gateway, and need an
`id` from `device_check` / `battery_modules` (`devMap[].id`):

```bash
franklinwh-local -i 192.0.2.110 battery_cells --id 1      # per-cell V + temps, SoC/SoH
franklinwh-local -i 192.0.2.110 power_electronics --id 1  # bus/grid/inverter V and A
franklinwh-local -i 192.0.2.110 device_firmware --id 1    # PE/BMS serials + versions
franklinwh-local -i 192.0.2.110 device_states --id 1      # DSP/main/PE/BMS states
```

Called **without** `id` they return the same keys with empty or zero values
(`result=1 reason=-1`) — easy to misread as "this command returns nothing".

### Connecting (Direct Connection)

The aGate exposes TCP/9000 on its **own WiFi hotspot** — the same "Direct
Connect" path the FranklinWH mobile app uses. To talk to it:

1. On the gateway/app, start **Direct Connect → Connect via aGate hotspot**.
2. Join the WiFi network `AP_<serial-suffix>` (e.g. `AP_F24170091`).
3. The gateway is the hotspot gateway IP (typically `10.100.1.1`). Point
   `LocalClient` / the CLI at it, or let the scanner find it:

   ```bash
   franklinwh-local scan gateway        # auto-targets the hotspot gateway
   franklinwh-local --host 10.100.1.1 power_flow
   ```

(The app also offers a Bluetooth Direct Connect path; only the WiFi/TCP path is
implemented here.)

### Discover devices on the LAN

```bash
franklinwh-local scan 10.100.1.0/24    # scan a subnet
franklinwh-local scan gateway          # just the hotspot gateway
franklinwh-local scan 10.0.0.0/24 --json
```

Detects open **TCP 9000** (sendMqtt) and **TCP 502** (Modbus), and by default
*confirms* a 9000 listener by performing the login handshake.

### Test without hardware (emulator)

```bash
franklinwh-local emulate --port 9000   # fake aGate replaying captured data
# then, in another shell:
franklinwh-local --host 127.0.0.1 power_flow
```

## CLI

```bash
franklinwh-local catalog                       # list known cmdType codes (grouped)
franklinwh-local catalog --grep bms            # filter by name/description/cloud call
franklinwh-local catalog --json                # ... as JSON, with cloud equivalents
franklinwh-local decode capture.pcap           # decode a pcap
franklinwh-local decode capture.pcap --json    # ... as JSON

franklinwh-local --host 10.100.1.1 power_flow  # live read
franklinwh-local --host 10.100.1.1 call 1301 --data '{"opt":0}'

franklinwh-local --host 10.100.1.1 power_flow --watch 5          # poll every 5s
franklinwh-local --host 10.100.1.1 power_flow --watch 5 --count 12
```

**Every name in `catalog` is a live subcommand** — the command list is generated from
the catalog, so the two cannot drift. `franklinwh-local -i <ip> grid_ov_trip` works just
as `power_flow` does, and anything uncatalogued is still reachable via `call <code>`.

`--watch [SECONDS]` (default 5) reuses one logged-in session and prints a line
per poll — a friendly summary for `power_flow`, compact JSON otherwise.
`--count N` stops after N samples (Ctrl-C otherwise).

## Control (live writes)

Confirmed working over LAN TCP/9000 (no SPAN unlock, no cloud) — see
[`catalog.WRITES`](franklinwh_local/catalog.py) and `docs/PROTOCOL.md`. The CLI
shape mirrors the sibling tools: `-i/--ip` for the aGate (as in
[franklinwh-modbus](https://github.com/david2069/franklinwh-modbus)), and a
get-or-`--set` command (as in
[franklinwh-cloud](https://github.com/david2069/franklinwh-cloud)):

```bash
franklinwh-local -i 192.0.2.110 mode                  # just the current mode
franklinwh-local -i 192.0.2.110 mode --list           # all modes + details
franklinwh-local -i 192.0.2.110 mode --json           # decoded dataArea (JSON)
franklinwh-local -i 192.0.2.110 mode --raw            # full on-the-wire frame (cmdType/snno/crc/...)
franklinwh-local -i 192.0.2.110 mode --set self       # set; alias tou / self / sc / backup
franklinwh-local -i 192.0.2.110 mode --set 29287      # ...or a programme id

franklinwh-local -i 192.0.2.110 offgrid               # show off-grid status
franklinwh-local -i 192.0.2.110 offgrid --set on --soc 5
franklinwh-local -i 192.0.2.110 offgrid --set off     # reconnect
```

In Python:

```python
from franklinwh_local import LocalClient
with LocalClient("192.0.2.110") as c:
    c.login()
    c.set_mode("tou")                  # 1727 {opt:3, current_id}; alias or full name or id
```

> These command a real battery system. `mode --set` reports `current_id`
> before→after so you can confirm it took. Some settings (e.g. smart-circuit SoC
> cut-off) still round-trip through the cloud — use `… call <cmd> --data '…'` to
> experiment with codes not yet wrapped.

## Finding new (write/control) commands

The catalog so far is reverse-engineered from *read* traffic. To discover the
**write/control** codes, capture the app while it issues a control action and
look for `cmdType`s not yet in the catalog. You don't need Wireshark — macOS/Linux
ship `tcpdump`, and this library de-obfuscates the frames (Wireshark would only
show ciphered bytes):

```bash
# 1. capture phone <-> aGate :9000 (Direct-Connect hotspot or LAN), then in the
#    app do ONE control action at a time (switch mode, start charge, toggle SC).
sudo tcpdump -i <iface> -s0 -w fwh.pcap 'tcp port 9000'

# 2. triage — lists every cmdType seen; flags the ones NOT in the catalog:
franklinwh-local analyze fwh.pcap
franklinwh-local analyze fwh.pcap --unknown    # just the candidate write codes
```

Or watch the conversation live with a **transparent decoding proxy** — redirect
the app's `:9000` to it (ARP-spoof + DNAT, or a host route); it forwards every
byte verbatim and prints each decoded frame, flagging unknown cmdTypes:

```bash
franklinwh-local proxy 192.0.2.110          # relay :9000 -> aGate:9000
franklinwh-local proxy 192.0.2.110 --listen 0.0.0.0:9000
franklinwh-local proxy 192.0.2.110 --record session.pcap   # capture on demand
#   session.pcap opens in Wireshark and re-decodes: franklinwh-local decode session.pcap
```

> Unknown **odd** codes captured during a control action are the requests; their
> `dataArea` carries the setpoint. Add confirmed codes to `catalog.py`.

Or sweep the gateway directly with **`probe`**, which tries several *request payload
shapes* per code rather than only the usual `{"opt":0}`:

```bash
franklinwh-local -i 192.0.2.110 probe                      # all uncatalogued odd codes
franklinwh-local -i 192.0.2.110 probe --range 1413-1699    # one block
franklinwh-local -i 192.0.2.110 probe --json > probe.json
```

Some reads are addressed **per battery**, not per gateway — the cloud API's per-cell BMS
read sends `{"fhpSn": "<aPower serial>", "type": 2|3}`. A code like that answers a plain
`{"opt":0}` probe with silence, so a single-shape sweep cannot find it. `probe`
auto-discovers the battery serials (from `battery_modules` + the login manifest), tries
each shape, reports which one produced data, and flags replies that look like per-cell
telemetry. It only ever sends reads — never `opt=1`.

> **Caution:** this sends cmdTypes whose semantics are unknown to a real battery system.
> The payload matrix is read-shaped by construction, but scope your sweeps (`--codes`,
> `--range`) rather than blanket-probing a production gateway.

## How the protocol works

A frame is one JSON object. The header is cleartext; everything from `"type"`
onward is obfuscated with a trivial position-based additive cipher:

```
{"cmdType":<N>,"equipNo":"<E>",   <- cleartext header
"type":...,"timeStamp":...,"snno":...,"len":<L>,"crc":"<C>","dataArea":{...}}
\------------------------ ciphered region (i = 0 here) ----------------------/

encrypt: c[i] = (p[i] + seed + i) & 0xFF
decrypt: p[i] = (c[i] - seed - i) & 0xFF
```

There is **no key**. `seed` is `0x3F` for normal frames and `0xA5` for the
pre-login `1101` handshake. Because the first plaintext byte is always `"`,
decoding is self-synchronizing — the seed is recovered from the first ciphered
byte, so any frame can be read without knowing the seed in advance.

Field rules: `len` is the byte length of the compact `dataArea` JSON, and `crc`
is its CRC32 (uppercase hex). Full details and the command catalog are in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Security note

The broker channel is plain TCP and the obfuscation is keyless, so anyone on the
LAN path can read and forge frames. Decoded payloads expose WiFi credentials,
device serials, firmware versions, and GPS/location. Treat the network segment
accordingly.

## Layout

```
franklinwh_local/
  protocol.py    cipher, Frame, encode/decode, FrameStream, pcap reader
  catalog.py     cmdType enum + descriptions
  transport.py   TCP client: connect, login, request/response
  client.py      high-level named commands
  cli.py         command-line entry point
tests/           pytest suite (driven by a real capture fixture)
docs/PROTOCOL.md protocol + command catalog
```

## License

MIT. Unofficial and not affiliated with or endorsed by FranklinWH.
