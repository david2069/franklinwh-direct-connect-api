# Using franklinwh-direct-connect

A practical, end-to-end guide. For the wire format and command catalog see
[PROTOCOL.md](PROTOCOL.md); for a quick overview see the top-level
[README](https://github.com/david2069/franklinwh-direct-connect-api/blob/main/README.md).

- [Install](#install)
- [Connect to the gateway (Direct Connection)](#connect-to-the-gateway-direct-connection)
- [CLI usage](#cli-usage)
- [Library usage](#library-usage)
- [Test without hardware (emulator)](#test-without-hardware-emulator)
- [Decode a packet capture](#decode-a-packet-capture)
- [Extending the command catalog](#extending-the-command-catalog)
- [Probing for undocumented cmdTypes](#probing-for-undocumented-cmdtypes)
- [Troubleshooting](#troubleshooting)

---

## Install

Requires Python 3.10+. No runtime dependencies — standard library only.

```bash
git clone https://github.com/david2069/franklinwh-direct-connect-api
cd franklinwh-direct-connect

python3 -m venv .venv          # create a virtualenv
source .venv/bin/activate      # activate it  (Windows: .venv\Scripts\activate)
pip install -e .               # add ".[test]" to run the test suite

franklinwh-direct-connect --version     # verify: prints "franklinwh-direct-connect 0.1.0"
```

`franklinwh-direct-connect` is a **console script** installed onto your `PATH` — not a
`.py` file in the repo. `python franklinwh-direct-connect ...` fails with
`can't open file`. If the command isn't found, either activate the venv, call it
by path (`.venv/bin/franklinwh-direct-connect-api`), or use the module form
`python -m franklinwh_direct_connect_api`.

The three similar names: PyPI distribution `franklinwh-direct-connect-api`, import package
`franklinwh_direct_connect_api`, CLI command `franklinwh-direct-connect`.

---

## Connect to the gateway (Direct Connection)

The aGate exposes the protocol on **TCP/9000 on its own WiFi hotspot** — the same
"Direct Connect → Connect via aGate hotspot" path the FranklinWH mobile app uses.

1. In the FranklinWH app, open **Direct Connect** and note the hotspot name,
   `AP_<serial-suffix>` (e.g. `AP_F24170091`).
2. On your computer, **join that WiFi network**.
3. The gateway is the hotspot's gateway IP — typically `10.100.1.1`. Confirm/find
   it with the scanner:

   ```bash
   franklinwh-direct-connect scan gateway          # auto-target the hotspot gateway
   # 10.100.1.1: 9000/sendMqtt CONFIRMED (IBG_SN=FAKEGATE90FJ09J6H4F2)
   ```

You're now ready to issue commands against `10.100.1.1`.

> The app also lists a Bluetooth Direct Connect path. That's a separate (BLE)
> transport and is **not** implemented here — only the WiFi/TCP path.

---

## CLI usage

Run `franklinwh-direct-connect --help` for the full list.

### Command taxonomy

Commands fall into two groups — **offline** (work on files/the LAN, no aGate) and
**live** (require `--host/-i`, connect to a real aGate over TCP 9000). Live commands are
almost all read-only; only a handful write.

| Group | Commands | Notes |
|-------|----------|-------|
| **Offline tooling** | `decode`, `analyze`, `proxy`, `catalog`, `scan`, `emulate` | No `--host` needed |
| **Live — reads** | `health`, `firmware`, `power_flow`, `mode` (no `--set`), `mode_list`, `mode_config`, `mode_soc`, `tou_schedule`, `grid_policy`, `grid_profile`, `install_profile`, `solar_pv`, `smart_circuits`, `smart_circuit_meter`, `relay_status`, `ibg_run_status`, `ibg_state`, `battery_inhibit`, `battery_modules`, `generator`, `event_block`, `device_info`, `cloud_config`, `connectivity`, `time_location`, `network_interfaces`, `network_switches`, `wifi_scan`, `wifi_config`, `login`, `der_comms` | Read-only; most support `--watch`/`--count` |
| **Live — writes** | `mode --set`, `offgrid --set`, `der_comms --set-modbus/--set-2030-5`, `reboot` | Hardware-verified; writes verify at the *interface* level |
| **Live — raw** | `call <cmdType>` | Read by default; `--data '{"opt":1,…}'` writes any cmdType (no verification) |

> **Writes verify at the interface level, not a config read-back.** `mode --set` and
> `offgrid --set` are confirmed to apply. `der_comms --set-modbus off` confirms `:502`
> actually stops; `--set-modbus on` needs a reboot to bind `:502` (`--and-reboot` chains
> it); `reboot` confirms via `:9000` down→up. Reserved-SoC (`1405`) stays **withheld** —
> silently discarded locally (cloud-only). See PROTOCOL_DESIGN_REQUIREMENTS.md.

### Offline (no hardware)

```bash
franklinwh-direct-connect catalog                       # list known cmdType codes
franklinwh-direct-connect decode capture.pcap           # decode a capture
franklinwh-direct-connect decode capture.pcap --json    # ... as JSON
```

### Discovery

```bash
franklinwh-direct-connect scan gateway                  # just the hotspot gateway
franklinwh-direct-connect scan 10.100.1.0/24            # a whole subnet
franklinwh-direct-connect scan 10.0.0.1-10.0.0.50 --json
franklinwh-direct-connect scan 10.0.0.0/24 --no-probe   # open-port check only, no login
```

Detects **TCP 9000** (sendMqtt) and **TCP 502** (Modbus); for 9000 it confirms
by performing the login handshake and reports the device `IBG_SN`.

### Live reads

`--host` is required. Login happens automatically (pass `--equip <serial>` to skip it).

```bash
franklinwh-direct-connect --host 10.100.1.1 power_flow
franklinwh-direct-connect --host 10.100.1.1 smart_circuits
franklinwh-direct-connect --host 10.100.1.1 network_interfaces
franklinwh-direct-connect --host 10.100.1.1 call 1301 --data '{"opt":0}'   # any cmdType
```

See the [command taxonomy](#command-taxonomy) above for the full list of named reads.
`call <cmdType>` issues any code directly (default dataArea `{"opt":0}`).

### Live writes

Writers verify at the interface level (not a config read-back). `mode`, `offgrid`, and
`der_comms` also **read** when given no `--set*` flag.

```bash
# Operating mode (1727) — mode switch applies locally (verified)
franklinwh-direct-connect --host 10.100.1.1 mode                       # show current mode
franklinwh-direct-connect --host 10.100.1.1 mode --set self            # switch to Self-Consumption

# Off-grid (1723)
franklinwh-direct-connect --host 10.100.1.1 offgrid --set on --soc 20  # island, hold 20% floor
franklinwh-direct-connect --host 10.100.1.1 offgrid --set off          # reconnect

# DER comms (1205) — asymmetric: OFF stops :502 now, ON needs a reboot to bind it
franklinwh-direct-connect --host 10.100.1.1 der_comms                        # read both statuses
franklinwh-direct-connect --host 10.100.1.1 der_comms --set-modbus off       # confirm; verifies :502 stops
franklinwh-direct-connect --host 10.100.1.1 der_comms --set-modbus on --and-reboot  # set + reboot + verify :502 up
franklinwh-direct-connect --host 10.100.1.1 der_comms --set-2030-5 off       # disable IEEE 2030.5

# Reboot (1721) — warns if 4G is enabled; --wait verifies it returns (and re-discovers a new IP)
franklinwh-direct-connect --host 10.100.1.1 reboot --wait
franklinwh-direct-connect --host 10.100.1.1 firmware                         # firmware/version block

# Raw write of any cmdType (no verification — use with care)
franklinwh-direct-connect --host 10.100.1.1 call 1723 --data '{"opt":1,"offgridSet":0,"offgridSoc":5}'
```

> Enabling **IEEE 2030.5 / SEP2** (`--set-2030-5 on`) hands battery dispatch to a DERMS
> server and prompts to confirm. Reserved-SoC (`1405`) remains **withheld** — it is
> silently discarded locally (cloud-only). See PROTOCOL_DESIGN_REQUIREMENTS.md.

### Watch / polling

```bash
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch          # every 5s
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 10        # every 10s
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 5 --count 12
```

`--watch [SECONDS]` reuses one logged-in session and prints a line per poll
(a friendly summary for `power_flow`, compact JSON otherwise). `--count N` stops
after N samples; otherwise Ctrl-C.

Example output:

```
13:18:05  soc=66.5%  grid=19W  solar=-9W  batt=509W  load=519W  mode=Self-Consumption
13:18:10  soc=66.6%  grid=14W  solar=-7W  batt=502W  load=509W  mode=Self-Consumption
```

---

## Library usage

### One-shot reads

```python
from franklinwh_direct_connect_api import LocalClient

with LocalClient("10.100.1.1") as c:
    manifest = c.login()             # 1101 -> 1102; caches equipNo
    print(manifest["IBG_SN"], manifest["protocolVer"])

    flow = c.power_flow()            # 1301 -> 1302
    print(f"SoC {flow['soc']}%  load {flow['p_load']}W  battery {flow['p_fhp']}W")

    print(c.smart_circuits())        # 1409 -> 1410
    print(c.network_interfaces())    # 1117 -> 1118
```

### Any command by number

```python
with LocalClient("10.100.1.1") as c:
    c.login()
    data = c.call(1201)              # time/location; default dataArea {"opt":0}
    data = c.call(1725, {"opt": 1})  # paged mode list with a custom dataArea
```

### Low-level transport (full Frame objects)

```python
from franklinwh_direct_connect_api import LocalTransport

with LocalTransport("10.100.1.1") as t:
    t.login()
    frame = t.request(1301, t.equip_no, {"opt": 0})
    print(frame.cmd_type, frame.snno, frame.verify(), frame.data_area)
```

### Build / parse a single frame (no socket)

```python
from franklinwh_direct_connect_api import encode_frame, decode_frame

wire  = encode_frame(1301, "FAKEGATE90FJ09J6H4F2", {"opt": 0})
frame = decode_frame(wire)
assert frame.verify()                # len + crc check
```

---

## Test without hardware (emulator)

The emulator is a fake aGate that replays canned responses (loaded from the
bundled capture, so values are realistic).

```bash
franklinwh-direct-connect emulate --port 9000
# in another shell:
franklinwh-direct-connect --host 127.0.0.1 power_flow
franklinwh-direct-connect scan gateway
```

In Python (handy for tests):

```python
from franklinwh_direct_connect_api import Emulator, LocalClient

with Emulator("127.0.0.1", 0) as emu:        # port 0 = pick a free port
    with LocalClient("127.0.0.1", emu.port) as c:
        c.login()
        print(c.power_flow())
```

---

## Decode a packet capture

If you sniff the hotspot traffic (e.g. with Wireshark/tcpdump), decode it:

```python
from franklinwh_direct_connect_api import iter_pcap_frames

for frame in iter_pcap_frames("capture.pcap"):
    print(frame.cmd_type, frame.name, frame.verify())
    print("   ", frame.data_area)
```

`iter_pcap_frames` handles TCP reassembly and per-frame seed detection, so both
logins and normal frames decode transparently.

---

## Extending the command catalog

When you observe a new `cmdType`, add it to
[`franklinwh_direct_connect_api/catalog.py`](https://github.com/david2069/franklinwh-direct-connect-api/blob/main/franklinwh_direct_connect_api/catalog.py):

```python
class Cmd(IntEnum):
    ...
    MY_NEW_READ = 1313          # response will be 1314

CATALOG[1313] = CmdInfo(1313, 1314, "my_new_read", "what it returns")
```

Then it's immediately usable via `c.call(1313)` and shows up in
`franklinwh-direct-connect catalog`. To expose it as a named method, add a one-liner to
[`client.py`](https://github.com/david2069/franklinwh-direct-connect-api/blob/main/franklinwh_direct_connect_api/client.py):

```python
def my_new_read(self):
    return self.call(Cmd.MY_NEW_READ)
```

---

## Energy history and rollups

The aGate stores daily energy history itself — a rolling window of roughly **105 days** —
and serves one day per request (`energy_history`, cmdType 1303):

```bash
franklinwh-direct-connect -i 192.0.2.110 energy_history --date 2026-09-10
```

96 quarter-hour points (`rec_time`, `p_uti`, `p_gen`, `p_fhp`, `p_load`), seven `kwh_*`
daily totals, and per-tariff splits. For each channel, `sharp + peak + flat + valley`
sums exactly to that channel's total.

### Week / month / year rollups

The gateway has **no** rollup call — the cloud's week/month/year figures are computed
cloud-side, and local `dayType` is echoed but ignored. `energy_rollup` does the same
arithmetic locally, one request per day:

```bash
franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period week
franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period month --date 2026-08-15
franklinwh-direct-connect -i 192.0.2.110 energy_rollup --period total --json
```

Periods use the same numbering as the cloud's `get_power_details(type=…)`:
`day`=1, `week`=2, `month`=3, `year`=4, `total`=5.

Because retention is ~105 days, longer periods are necessarily partial. Every result
reports its own **coverage** rather than presenting a short sum as a full period:

```
week 2026-09-07 .. 2026-09-11   5/5 days

channel           total     sharp      peak      flat    valley
---------------------------------------------------------------
kwh_sun        101.8760    0.0000    1.2743   99.9804    0.6211
kwh_fhp_chg     57.7883    0.0000    0.0000   57.5574    0.2310
```

`--stop-after-empty N` (default 5) stops walking back once N consecutive days come back
empty — history is contiguous, so this avoids requesting a year of discarded dates.

## Building interval history (bridge territory)

`1303` cannot give you per-interval **load** or **solar** — its `p_load` series is a copy
of `p_fhp` and there is no `p_sun` series at all (see
[CLOUD_MAPPING.md §3c](CLOUD_MAPPING.md)). The live read `1301` reports both correctly, so
the fix is to poll `1301` and store the samples.

**That storage belongs in the bridge, not here.** This library is the local leg only —
protocol in, payloads out. Databases, retention, multi-gateway, REST and UI are the
bridge's job (see BACKLOG `EPIC-CLOUD-ALIGN`).

What the library gives a poller:

```python
from franklinwh_direct_connect_api import LocalClient, energy

with LocalClient("192.0.2.110") as c:
    c.login()
    s = c.power_flow()          # 1301 — poll this on your interval
    s["p_sun"], s["p_load"]     # both correct here, unlike 1303
    s["soc"], s["run_status"], s["mode"]
```

Relevant fields per sample: `p_sun`, `p_gen`, `p_fhp`, `p_uti`, `p_load` (watts), `soc`,
`t_amb`, `run_status`, `mode`, the running daily `kwh_*` totals, and the live
`sharp`/`peak`/`flat`/`valley` accumulators.

Sign conventions, matching the gateway's own daily totals: `p_uti` negative = export /
positive = import; `p_fhp` positive = discharge / negative = charge.

### Tariff-tier transitions

The tier arrays on `1301` are **running accumulators** that tick up through the day and
reset at midnight. Whichever grew between two samples is the tier the device considered
active — the only direct way to see *when* the boundary moves
(BACKLOG `DEF-1303-TIER-BASIS`; daily totals show the split but never the timing):

```python
energy.active_tier(sample, previous)        # -> "flat" | "peak" | ... | None
energy.tier_transitions(samples)            # -> [(ts, "flat", "peak"), ...]
```

Both are stateless helpers over payload dicts — sampling and persistence stay with the
caller.


## Battery Management (per-cell BMS)

```bash
franklinwh-direct-connect -i 192.0.2.110 battery              # one snapshot
franklinwh-direct-connect -i 192.0.2.110 battery --watch 2    # refresh every 2s, Ctrl-C to stop
franklinwh-direct-connect -i 192.0.2.110 battery --watch 5 --for 10m
franklinwh-direct-connect -i 192.0.2.110 battery --json > bms.json
```

Combines `1705` (per-cell voltages/temps, SoC/SoH), `1703` (grid and DC-bus rails),
`1835` (states) and `1833` (serials/firmware) in **one session** — all local, no cloud,
works on the Direct-Connect hotspot. `bms` is an alias.

```
🔬 Cell Telemetry (16 series)
              Highest: 3318 mV   (cell 13)
               Lowest: 3316 mV   (cell 1)
               Spread: 2 mV
           Temp Range: 20.5°C → 21.4°C   (cells 1–11)

  #1        #2        #3        #4        ...
  ↓3.316V    3.317V    3.317V    3.317V
   20.5°C    20.7°C    20.8°C    20.8°C
```

`↓`/`↑` mark the lowest/highest cell and `*` the hottest; those positions are derived
from the arrays, so nothing is lost versus the cloud's `minVolPos`/`maxVolPos` fields.
Spread is coloured green ≤20 mV, amber ≤50 mV, red above.

### Monitoring

| flag | effect |
|---|---|
| `--watch [SECONDS]` | refresh every SECONDS (default 5) |
| `--for DURATION` | stop after `90`, `30s`, `5m`, `2h` |
| `--count N` | stop after N samples |
| `--id N` | which aPower (from `device_check` `devMap[].id`) |

Ctrl-C stops at any time. On a terminal the view **repaints in place**; piped or
redirected output **appends**, so a log keeps every sample rather than a pile of escape
codes. A dropped read during monitoring is reported and the session continues — this link
is flaky by nature, so one bad poll should not end a ten-minute watch.

Colour auto-disables when output is not a terminal, and honours `NO_COLOR`;
`--no-colour` forces plain text.

> **Local only.** Thermal sensors (device/inverter/LLC/buck-boost), cell balancing state
> and MOS/fan/heater state are **not** on the local channel — they come from the cloud's
> `get_bms_info()` "Layer 2" payload. Rows that cannot be filled are omitted rather than
> shown blank. See [CLOUD_MAPPING.md §3e](CLOUD_MAPPING.md).

## TOU schedule

```bash
franklinwh-direct-connect -i 192.0.2.110 tou            # readable blocks
franklinwh-direct-connect -i 192.0.2.110 tou --bar      # with a 24-column day bar
franklinwh-direct-connect -i 192.0.2.110 tou --json
```

Decodes cmdType 1407's parallel arrays into ordered tariff blocks, and shows the
gateway's own local time, timezone and DST flag (from 1201) so weekday/weekend is
resolvable:

```
gateway time: 2026-09-11 17:54:08 Friday  (UTC+10, DST=on)

workday (5 blocks)
  00:00–00:30  tier 2 On-Peak
  00:30–02:00  tier 1 Mid-Peak
  02:00–04:00  tier 0 Off-Peak
  04:00–23:00  tier 1 Mid-Peak
  23:00–24:00  tier 2 On-Peak
```

> **Tariff only.** The per-block *dispatch* action (Standby, Self-Consumption, Grid
> Export …) the app shows beside each block is **not** on the local channel — see
> [CLOUD_MAPPING.md §3d](CLOUD_MAPPING.md).

## Probing for undocumented cmdTypes

`probe` sweeps request codes against a live aGate and, for each one, tries several
**request payload shapes** — not just the usual `{"opt": 0}`.

```bash
franklinwh-direct-connect -i 192.0.2.110 probe                       # uncatalogued odd codes
franklinwh-direct-connect -i 192.0.2.110 probe --range 1413-1699     # one block
franklinwh-direct-connect -i 192.0.2.110 probe --codes 1207,1209     # specific codes
franklinwh-direct-connect -i 192.0.2.110 probe --plain-only          # old single-shape sweep
franklinwh-direct-connect -i 192.0.2.110 probe --json > probe.json
```

### Why the payload matrix matters

Every read this library issues is addressed to the **aGate** with `{"opt": 0}`. But not
every read is gateway-addressed: the cloud API's per-cell BMS read sends its cmdType with
`{"fhpSn": "<aPower serial>", "type": 2}` (and again with `type: 3`) — parameterised **per
battery**. A code expecting that selector answers an `{"opt": 0}` probe with silence or an
empty envelope, which looks exactly like "this code does not exist".

So `probe` tries, per code: `{"opt":0}`, `{"fhpSn":SN}`, `{"fhpSn":SN,"type":2}`,
`{"fhpSn":SN,"type":3}`, `{"opt":0,"fhpSn":SN}` — and reports **which shape** worked.
Serials are auto-discovered from `battery_modules` (1831) and the login manifest
(`FHP_SN`/`BMS_SN`); override with `--serial SN` or skip with `--no-serials`.

By default the sweep **stops at the first shape that responds** — fastest when the
question is "does this code exist?". Use **`--all-shapes`** when a code *already* answers
`{"opt":0}` but looks thin: it tries every shape, prints each result side by side, and
keeps the richest reply. Without it, a code that answers the very first shape never gets
the selector shapes tried at all.

### Custom payloads

`--payload` (repeatable) replaces the default matrix with your own shapes. `%fhpSn%`
expands to each discovered serial:

```bash
franklinwh-direct-connect -i 192.0.2.110 probe --codes 1507 \
  --payload '{"opt":0}' \
  --payload '{"opt":0,"fhpSn":"%fhpSn%"}' \
  --payload '{"fhpSn":"%fhpSn%","type":4}'
```

A payload carrying `opt` set to anything but `0` is refused — `opt=1` is the **write**
convention, and `probe` is a read-only tool.

### Reading the output

```
1507   HIT      [fhpSn,type]  17 keys: fhpSn, vol1, vol10, vol11, …  CELL-LIKE:vol*  <-- NEW
1509   envelope-only (responded, no data)
1511   timeout
```

- `HIT` — the reply carried data beyond the `opt`/`result`/`reason` envelope.
- `<-- NEW` — the code is not in `catalog.CATALOG`.
- `CELL-LIKE:<series>` — ≥8 numeric values clustered in a plausible cell-voltage band
  (2.0–5.0 V or 2000–5000 mV). That is the signature of per-cell telemetry.
- The closing summary counts how many hits **needed** an `fhpSn` selector — i.e. how many
  a plain `opt=0` sweep would have missed.

The set of "already known" codes is derived from the catalog, so the swept range never
goes stale as `catalog.py` grows.

### Safety

Every shape `probe` sends is a read — `opt=0` or a selector; it never sends `opt=1`
(the write convention). But it does send cmdTypes whose semantics are **unknown**, to a
real battery system. Scope your sweeps with `--codes`/`--range` rather than blanket
probing, and add confirmed finds to `catalog.py` so the next sweep skips them.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `python: can't open file '.../franklinwh-direct-connect-api'` | Drop the `python` — it's a console script, not a `.py` file. Just `franklinwh-direct-connect ...`. |
| `command not found: franklinwh-direct-connect` | Venv not activated (`source .venv/bin/activate`) or `pip install -e .` not run in it. Or use `python -m franklinwh_direct_connect_api ...`. |
| `No module named franklinwh_direct_connect_api` | Wrong interpreter — `which python` and `pip -V` should both point inside `.venv`. |
| `scan gateway` finds nothing | Not joined to the `AP_<serial>` hotspot, or the gateway isn't the subnet `.1` — try `scan <subnet>/24`. |
| Connection refused on 9000 | The aGate only listens on its hotspot, not your normal LAN. Use Direct Connect. |
| `TimeoutError` on a read | Increase `--timeout`; only one `sendMqtt` exchange happens at a time, so avoid concurrent clients. |
| `call` returns `{"result": <non-zero>}` | The gateway rejected the request (bad `opt`/dataArea for that cmdType). |
| Decoded `dataArea` looks wrong | File a capture — the seed auto-detects, but an unseen frame layout may need catalog work. |

> **Security:** the channel is plain TCP with keyless obfuscation. Anyone on the
> hotspot can read/forge frames, and payloads include WiFi credentials and
> location. Only use on networks you control.
