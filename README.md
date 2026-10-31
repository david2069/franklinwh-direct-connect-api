# franklinwh-direct-connect-api

This library is a **proof-of-concept demonstration** of how to talk to a FranklinWH aGate
gateway over the (undocumented, unofficial) **FranklinWH Direct Connect** local API — the
JSON `cmdType` frames exchanged over **TCP/9000**. It is the lower-level device↔broker
channel that the cloud `sendMqtt` REST relay (see
[`franklinwh-cloud`](https://github.com/david2069/franklinwh-cloud)) is layered on top of.

**On the names.** *Direct Connect* is FranklinWH's own term for the gateway's local
protocol. This project implements that protocol; it is the **library and CLI**, not an
application — the [Direct Connect
Bridge](https://github.com/david2069/franklinwh-direct-connect-bridge) is the application
built on top of it, and is where a REST API, MQTT, Home Assistant entities and a web UI
live. Adopting FranklinWH's term implies **no affiliation with, endorsement by, or support
from FranklinWH**.

The distribution on PyPI is `franklinwh-direct-connect-api`, the import package is
`franklinwh_direct_connect_api`, and the CLI command is `franklinwh-direct-connect`. The
pre-0.4.0 spellings still work, because removing them would break existing code: importing
`franklinwh_local` returns the *same* module objects (so `isinstance` and subclassing hold
across both spellings), the `franklinwh-local` command is the same entry point, and
`LocalClient`/`LocalTransport` remain aliases of `DirectConnectClient`/
`DirectConnectTransport`. Importing the old package emits a `DeprecationWarning`, and the
aliases are **scheduled for removal in 0.6.0** — the date was previously 0.5.0, which
shipped with them still in place.

**It is not intended for production use, and there is no guarantee it is compatible with
your FranklinWH gateway(s), aPower(s) or connectivity — now or in the future.** FranklinWH
***<u>may change, block or deprecate this interface at any time</u>***. It has been tested on a local
area network against **one** aGate X with **one** aPower, most recently on firmware
`IBG_VER V12R02B60D00_260924` / `protocolVer V1.12.02` (read 2026-10-31). One site on one
firmware is a hypothesis, not a compatibility matrix: multi-aPower behaviour in particular
is **unobserved**, and anything this documentation marks UNCONFIRMED has not been proven on
any hardware.

**You do not need a gateway to try it.** Run the built-in emulator and point the whole CLI
and library at it — a deterministic synthetic aGate with N aPowers, live telemetry, energy
history, smart circuits and writes that persist, so you can see the thing work before you
connect real hardware:

```bash
franklinwh-direct-connect emulate                       # a fake aGate (port 19000)
franklinwh-direct-connect --host 127.0.0.1 --port 19000 power_flow  # ... talk to it
```

> **TCP 9000 is a reserved port and not available to this emulator.** It **refuses to start
> on 9000** and defaults to **19000**. `9000` belongs to a real aGate and to the
> [FranklinWH Gateway Emulator](https://github.com/david2069/franklinwh-gateway-emulator) —
> the official emulator, which is deliberately *transparent*, so something answering on
> 9000 is meant to be indistinguishable from a gateway. This library's mock must stay
> distinguishable from one: a mock left on 9000 once showed up in a LAN scan as
> `9000/sendMqtt CONFIRMED`, which makes every discovery result untrustworthy.
>
> **`proxy` is the exception** and still listens on `0.0.0.0:9000`: it relays every byte
> to a *real* aGate and never answers on its own behalf, so a client reaching it is
> talking to the gateway. Sitting on `:9000` between the app and the device is the point
> of that tool.

The emulator is a development aid. It serves what it was told to serve, so it is **not**
evidence of how real hardware behaves.

> **Status: alpha.** The protocol was reverse-engineered from packet captures.
> Frame parsing/encoding and the offline tooling are well tested; live transport
> against real hardware should be validated on your own LAN.
>
> This is still work in progress - as some functions have not been fully tested and/or exposed yet.
>
> For example (there may be others):
> - set operating mode specific reserved state of change
> - battery dispatch to force charge and discharge
> - set battery or grid inverter power (in watts) for battery dispatch operations
> - determining battery capabilities for the AC inverter (in watts) and battery capacity (in watt hours)

## Why this exists

A FranklinWH aGate can be reached three different ways:

- **The FranklinWH Cloud API** — what the official **mobile app** and the **FleetView**
  installer portal use. Capable, but it routes through FranklinWH's servers and needs an
  account and an internet connection.
- **Modbus TCP (SunSpec)** — a standards-based local interface. Good for basic power/energy
  reads and a few setpoints, but only a narrow slice of what the device actually knows.
- **The aGate's own local broker protocol** — the proprietary `sendMqtt` `cmdType` channel
  on **TCP/9000** that the app itself speaks under the hood. The official FranklinWH app
  calls this interface **"Direct Connect."** This is what this library implements.

The project exists to demonstrate that third path: a fully **local, no-cloud, no-account**
way to **query, control, and administer** an aGate directly on your LAN — no FranklinWH
servers, no Modbus gateway required. Because it's the device's *native* channel, it surfaces
the deep structural telemetry the cloud strips out to keep the app fast (per-cell battery
voltages, relay/contactor states, full physics arrays), plus configuration and control
(operating mode, off-grid, reboot) — things neither a plain Modbus read nor the cloud expose
together in one place.

## ⚖️ Disclaimer

> **UNOFFICIAL SOFTWARE — NOT AFFILIATED WITH OR ENDORSED BY FRANKLINWH.**
>
> This library speaks FranklinWH's undocumented **Direct Connect** (local) protocol on
> **TCP/9000** — technically the **same private channel the official FranklinWH mobile app**
> uses, intended for that app and not for third-party use. It
> ***<u>may change, break, or become unavailable without notice</u>***. It is provided **AS-IS**, without warranty of any kind, express
> or implied — use entirely at your own risk. The authors accept no liability for service
> interruptions, data loss, equipment damage, or any other consequences of using this
> software.
>
> **On the name "Direct Connect":** the official FranklinWH app uses this label for the local
> interface; this project adopts the term **purely to identify the same channel**. It implies
> **no affiliation with, endorsement by, or support from FranklinWH** — this is unofficial,
> reverse-engineered software.
>
> **Do NOT contact FranklinWH support** about this software. Raise issues, defects, or feature
> requests on GitHub instead:
> <https://github.com/david2069/franklinwh-direct-connect-api/issues>

### Compliance & anti-circumvention

> You agree to keep your gateway and battery settings, controls, and operation compliant with
> the configuration set through the official FranklinWH Mobile App and the installer/support
> FleetView portal.
>
> FranklinWH-managed settings may exist to, among other things: protect the **safety and
> longevity** of the battery and gateway; apply **automatic software updates** and restrict
> your ability to view or change battery, grid-import, or grid-export controls; enforce your
> **local grid profile** and any import/export limits or prohibitions; and enforce
> restrictions tied to **contractual incentives, subsidies, or VPP/grid programmes**.
>
> If you use this software to bypass or override any such control, restriction, or compliance
> measure — deliberately or inadvertently — you do so **entirely at your own risk**. This is
> neither condoned nor encouraged by the authors or any other party.
>
> This software is provided for **informational and educational purposes**, **AS-IS**, with no
> warranty of fitness for any purpose. Any use — personal or commercial — is permitted under
> the MIT License and is entirely at your own risk.
>
> As the MIT License requires, the copyright notice and this notice (including the Additional
> Terms) should be included in copies or substantial portions of the software — in forks,
> derivatives, and AI-assisted works alike, so the unofficial-app and compliance context
> travels with the code. See [`LICENSE`](LICENSE) (Additional Terms) for the authoritative
> text.

**Docs:** <https://david2069.github.io/franklinwh-direct-connect-api/> — [Usage](https://david2069.github.io/franklinwh-direct-connect-api/USAGE/) (full how-to) · [Protocol & catalog](https://david2069.github.io/franklinwh-direct-connect-api/PROTOCOL/) (wire format + command catalog) · [API reference](https://david2069.github.io/franklinwh-direct-connect-api/API/). The same pages as markdown: [`docs/`](docs/).

## Setup

Requires **Python 3.10+**. No runtime dependencies (standard library only).

```bash
python3 -m venv .venv          # 1. create a virtualenv
source .venv/bin/activate      # 2. activate it  (Windows: .venv\Scripts\activate)
pip install franklinwh-direct-connect-api

franklinwh-direct-connect --version     # 3. verify
# franklinwh-direct-connect 0.4.0
```

To work on it instead, install the checkout editable — add `[test]` for the pytest suite:

```bash
git clone https://github.com/david2069/franklinwh-direct-connect-api
cd franklinwh-direct-connect-api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest -m "not live"           # offline suite; "live" tests need a real aGate
```

### How to run it

`franklinwh-direct-connect` is a **console script** that `pip install` puts on your
`PATH` — it is *not* a `.py` file in this repo, so these do **not** work:

```bash
python franklinwh-direct-connect ...        # can't open file '.../franklinwh-direct-connect'
python franklinwh_direct_connect_api.py ...     # no such file
```

Run it one of these three ways:

```bash
franklinwh-direct-connect catalog                    # venv activated (recommended)
.venv/bin/franklinwh-direct-connect catalog          # venv not activated — call it by path
python -m franklinwh_direct_connect_api catalog          # module form; works anywhere the package imports
```

One name throughout, as of 0.4.0: distribution **`franklinwh-direct-connect-api`**, import
package **`franklinwh_direct_connect_api`**, CLI **`franklinwh-direct-connect`**. **Direct
Connect** is FranklinWH's own term for this protocol.

### Migrating from 0.3.x and earlier

The import package was `franklinwh_local` and the CLI was `franklinwh-local`. Both still
work and emit a `DeprecationWarning`; **they are scheduled for removal in 0.6.0**.

```python
from franklinwh_local import LocalClient                         # 0.3.x — deprecated
from franklinwh_direct_connect_api import DirectConnectClient     # 0.4.0 onward
```

The alias re-exports the *same* objects, so `isinstance`, subclassing and `is` comparisons
hold across both spellings — you can migrate file by file. `LocalClient` and
`LocalTransport` also remain as aliases of `DirectConnectClient` / `DirectConnectTransport`.
To find every remaining use, run with `PYTHONWARNINGS=error::DeprecationWarning`.

For a ready-made application built on this library — REST API, MQTT / Home Assistant
entities and a web UI — see the
[FranklinWH Direct Connect Bridge](https://github.com/david2069/franklinwh-direct-connect-bridge).

Everything below assumes the venv is activated. Offline commands
(`catalog`, `decode`, `analyze`, `emulate`) need no hardware — start with
`franklinwh-direct-connect catalog` to confirm your install works.

### Troubleshooting the install

| Symptom | Cause / fix |
| --- | --- |
| `can't open file '.../franklinwh-direct-connect'` | You ran `python franklinwh-direct-connect`. Drop the `python` — it's a command, not a script. |
| `command not found: franklinwh-direct-connect` | The venv isn't activated (`source .venv/bin/activate`), or `pip install -e .` hasn't been run in it. |
| `No module named franklinwh_direct_connect_api` | You're on a different interpreter than the one you installed into. Check with `which python` and `pip -V` — both should point inside `.venv`. |
| `DeprecationWarning: 'franklinwh_local' was renamed` | Expected whenever you import the old name (it still works). See [Migrating](#migrating-from-03x-and-earlier); it stops working at 0.5.0. |
| `error: externally-managed-environment` | You ran `pip install` outside a venv on a Homebrew/system Python. Create and activate the venv first. |

## Quick start

Decode a capture (offline, no hardware):

```python
from franklinwh_direct_connect_api import iter_pcap_frames

for frame in iter_pcap_frames("capture.pcap"):
    print(frame, frame.data_area)
```

Build and parse a single frame:

```python
from franklinwh_direct_connect_api import encode_frame, decode_frame

wire  = encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0})  # power-flow poll
frame = decode_frame(wire)
assert frame.verify()          # len + crc check
```

Talk to a live gateway:

```python
from franklinwh_direct_connect_api import DirectConnectClient

with DirectConnectClient("10.100.1.1") as c:   # the hotspot gateway IP
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
franklinwh-direct-connect -i 192.0.2.110 battery            # per-cell view
franklinwh-direct-connect -i 192.0.2.110 battery --watch 2 --for 10m
```

Per-cell voltages and temperatures, pack SoC/SoH, bus rails and states — one session,
local only. `--watch`/`--for`/`--count` monitor continuously; Ctrl-C stops.

### Per-device reads

Four reads are addressed to a **specific device** rather than the gateway, and need an
`id` from `device_check` / `battery_modules` (`devMap[].id`):

```bash
franklinwh-direct-connect -i 192.0.2.110 battery_cells --id 1      # per-cell V + temps, SoC/SoH
franklinwh-direct-connect -i 192.0.2.110 power_electronics --id 1  # bus/grid/inverter V and A
franklinwh-direct-connect -i 192.0.2.110 device_firmware --id 1    # PE/BMS serials + versions
franklinwh-direct-connect -i 192.0.2.110 device_states --id 1      # DSP/main/PE/BMS states
```

Called **without** `id` they return the same keys with empty or zero values
(`result=1 reason=-1`) — easy to misread as "this command returns nothing".

### Connecting (Direct Connection)

The aGate exposes TCP/9000 on its **own WiFi hotspot** — the same "Direct
Connect" path the FranklinWH mobile app uses. To talk to it:

1. On the gateway/app, start **Direct Connect → Connect via aGate hotspot**.
2. Join the WiFi network `AP_<serial-suffix>` (e.g. `AP_F24170091`).
3. The gateway is the hotspot gateway IP (typically `10.100.1.1`). Point
   `DirectConnectClient` / the CLI at it, or let the scanner find it:

   ```bash
   franklinwh-direct-connect scan gateway        # auto-targets the hotspot gateway
   franklinwh-direct-connect --host 10.100.1.1 power_flow
   ```

(The app also offers a Bluetooth Direct Connect path; only the WiFi/TCP path is
implemented here.)

### Discover devices on the LAN

```bash
franklinwh-direct-connect scan 10.100.1.0/24    # scan a subnet
franklinwh-direct-connect scan gateway          # just the hotspot gateway
franklinwh-direct-connect scan 10.0.0.0/24 --json
```

Detects open **TCP 9000** (sendMqtt) and **TCP 502** (Modbus), and by default
*confirms* a 9000 listener by performing the login handshake.

### Test without hardware (emulator)

```bash
franklinwh-direct-connect emulate               # fake aGate replaying captured data
# then, in another shell:
franklinwh-direct-connect --host 127.0.0.1 power_flow
```

## CLI

```bash
franklinwh-direct-connect catalog                       # list known cmdType codes (grouped)
franklinwh-direct-connect catalog --grep bms            # filter by name/description/cloud call
franklinwh-direct-connect catalog --json                # ... as JSON, with cloud equivalents
franklinwh-direct-connect decode capture.pcap           # decode a pcap
franklinwh-direct-connect decode capture.pcap --json    # ... as JSON

franklinwh-direct-connect --host 10.100.1.1 power_flow  # live read
franklinwh-direct-connect --host 10.100.1.1 call 1301 --data '{"opt":0}'

franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 5          # poll every 5s
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 5 --count 12
```

**Every name in `catalog` is a live subcommand** — the command list is generated from
the catalog, so the two cannot drift. `franklinwh-direct-connect -i <ip> grid_ov_trip` works just
as `power_flow` does, and anything uncatalogued is still reachable via `call <code>`.

`--watch [SECONDS]` (default 5) reuses one logged-in session and prints a line
per poll — a friendly summary for `power_flow`, compact JSON otherwise.
`--count N` stops after N samples (Ctrl-C otherwise).

## Control (live writes)

> ⚠️ **These commands change a live energy system.** Operating mode, off-grid/island state
> and reboot all take effect on real hardware immediately, and some are not visibly reversible
> from this library alone. Read
> [Compliance & anti-circumvention](#compliance--anti-circumvention) before using them, and
> **confirm every change in the official FranklinWH app** afterwards — the app is the
> authoritative view of what your gateway is actually doing, and a write that this library
> reports as accepted is not proof the device applied it.

Confirmed working over LAN TCP/9000 (no SPAN unlock, no cloud) — see
[`catalog.WRITES`](franklinwh_direct_connect_api/catalog.py) and `docs/PROTOCOL.md`. The CLI
shape mirrors the sibling tools: `-i/--ip` for the aGate (as in
[franklinwh-modbus](https://github.com/david2069/franklinwh-modbus)), and a
get-or-`--set` command (as in
[franklinwh-cloud](https://github.com/david2069/franklinwh-cloud)):

```bash
franklinwh-direct-connect -i 192.0.2.110 mode                  # just the current mode
franklinwh-direct-connect -i 192.0.2.110 mode --list           # all modes + details
franklinwh-direct-connect -i 192.0.2.110 mode --json           # decoded dataArea (JSON)
franklinwh-direct-connect -i 192.0.2.110 mode --raw            # full on-the-wire frame (cmdType/snno/crc/...)
franklinwh-direct-connect -i 192.0.2.110 mode --set self       # set; alias tou / self / sc / backup
franklinwh-direct-connect -i 192.0.2.110 mode --set 29287      # ...or a programme id

franklinwh-direct-connect -i 192.0.2.110 offgrid               # show off-grid status
franklinwh-direct-connect -i 192.0.2.110 offgrid --set on --soc 5
franklinwh-direct-connect -i 192.0.2.110 offgrid --set off     # reconnect
```

In Python:

```python
from franklinwh_direct_connect_api import DirectConnectClient
with DirectConnectClient("192.0.2.110") as c:
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
franklinwh-direct-connect analyze fwh.pcap
franklinwh-direct-connect analyze fwh.pcap --unknown    # just the candidate write codes
```

Or watch the conversation live with a **transparent decoding proxy** — redirect
the app's `:9000` to it (ARP-spoof + DNAT, or a host route); it forwards every
byte verbatim and prints each decoded frame, flagging unknown cmdTypes:

```bash
franklinwh-direct-connect proxy 192.0.2.110          # relay :9000 -> aGate:9000
franklinwh-direct-connect proxy 192.0.2.110 --listen 0.0.0.0:9000
franklinwh-direct-connect proxy 192.0.2.110 --record session.pcap   # capture on demand
#   session.pcap opens in Wireshark and re-decodes: franklinwh-direct-connect decode session.pcap
```

> Unknown **odd** codes captured during a control action are the requests; their
> `dataArea` carries the setpoint. Add confirmed codes to `catalog.py`.

Or sweep the gateway directly with **`probe`**, which tries several *request payload
shapes* per code rather than only the usual `{"opt":0}`:

```bash
franklinwh-direct-connect -i 192.0.2.110 probe                      # all uncatalogued odd codes
franklinwh-direct-connect -i 192.0.2.110 probe --range 1413-1699    # one block
franklinwh-direct-connect -i 192.0.2.110 probe --json > probe.json
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

There is **no key**, and the `seed` is **derived from the serial** in the `equipNo`
header — `(sum(utf8(equipNo)) + len(equipNo) + 29) mod 256`. That yields `0xA5` for the
pre-login `1101` handshake (`"00000000"`) and `0x3F` for the reference gateway's 20-char
serial; another serial gives another seed, so it must be derived, not hardcoded. Because
the first plaintext byte is always `"`, *decoding* is self-synchronizing — the seed is
recovered from the first ciphered byte, so any frame can be read without knowing the
serial. (The formula is `voidstarr/franklinwh_local`'s finding; see
[`docs/PROTOCOL.md`](docs/PROTOCOL.md).)

Field rules: `len` is the byte length of the compact `dataArea` JSON, and `crc`
is its CRC32 (uppercase hex). Full details and the command catalog are in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Security note

The broker channel is plain TCP and the obfuscation is keyless, so anyone on the
LAN path can read and forge frames. Decoded payloads expose WiFi credentials,
device serials, firmware versions, and GPS/location. Treat the network segment
accordingly.

**Before you attach anything to an issue.** Packet captures, `.pcap` files and the output of
`--raw`, `proxy` and `probe` contain those same values in clear — WiFi credentials, serial
numbers, firmware versions and your location. **Redact them first**: replace serials and
MACs with placeholders, and use the documentation address ranges (`192.0.2.x`) rather than
your own. A capture posted to a public issue is a capture published.

## Layout

```
franklinwh_direct_connect_api/
  protocol.py    cipher, Frame, encode/decode, FrameStream, pcap reader
  catalog.py     cmdType catalog + enums (RUN_STATUS, WRITES, OPERATING_MODES)
  transport.py   TCP client: connect, login, request/response (serialised)
  client.py      high-level named commands (reads + the six writes)
  cli.py         command-line entry point
  discover.py    LAN scan for :9000 / :502
  emulator.py    fake aGate broker, backed by synthetic.py
  synthetic.py   deterministic per-seed synthetic site
  energy.py      1303/1407 helpers: rollups, TOU blocks, tariff tiers
  bms.py         per-cell battery rendering for the `battery` command
  probe.py       read-only cmdType sweep with a payload matrix
  proxy.py       transparent decoding relay
franklinwh_local/  deprecated import shim (to be removed in 0.6.0)
tests/           pytest suite (emulator- and capture-driven)
docs/            the published guide (mkdocs): USAGE, PROTOCOL, API, CLOUD_MAPPING
```

## License

MIT, plus **Additional Terms** — unofficial and not affiliated with or endorsed by
FranklinWH, with a compliance and anti-circumvention clause. See [`LICENSE`](LICENSE) for the
authoritative text and [Disclaimer](#️-disclaimer) for the readable version.
