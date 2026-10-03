# FranklinWH Local API — Protocol Design Requirements

> **Read this before writing any code that talks to a live aGate.** These are hard
> requirements learned from live-hardware behaviour. They apply to every agent and
> contributor. Companion to [AGENT.md](AGENT.md); protocol details in
> [docs/PROTOCOL.md](docs/PROTOCOL.md).

The local API is the Direct-Connect **sendMqtt** protocol on **TCP/9000** (JSON frames
keyed by integer `cmdType`). It is **grid-profile-agnostic** — cmdTypes are just settings;
values reflect whatever profile/config the site has loaded. Do not hardcode grid standards,
regions, or countries into names or descriptions.

---

## R1 — Writes MUST send the full block (read-modify-write)

The aGate **rejects partial config frames** with `result:1` (often `reason:-2`). A write
must read the current block, overlay only the changed fields, and send the **entire block
back** with `opt:1`.

- Verified: reserved-SoC (`1405`), der_comms (`1205`), and device reboot (`1721`) all
  reject a partial frame and accept the full block.
- Never construct a write payload from only the fields you want to change.

```python
prior = client.call(cmd)                       # read the whole block
block = {k: v for k, v in prior.items() if k not in ("opt", "result", "reason")}
block[field] = new_value                        # overlay only what changed
reply = client.call(cmd, {"opt": 1, **block})   # write the FULL block back
```

## R2 — `result:0` is NOT proof the change applied; verify at the interface level

A `result:0` reply, and even a read-back of the *config field*, do **not** prove the
setting took effect. Always verify the **actual effect / service**, not just the flag.

- **Silent discard:** some writes ACK `result:0` but never persist. Reserved-SoC (`1405`)
  is silently discarded locally — reserve is cloud-only. `set_mode_soc` read-back-verifies
  and raises on this.
- **Apply timing is not immediate, and is firmware-dependent.** `der_comms` `sunsMdEn`
  writes are **delayed-apply** (`:502` changes state a few seconds after the write) on FW
  `V12R02B30D06`, but on older firmware OFF was immediate and **ON required a reboot**. So:
  **poll the interface over a short window** (e.g. 30s) for the expected state — do not
  check once — and fall back to a reboot only if it doesn't converge. Some settings
  genuinely **require a reboot** to take effect; document apply timing per setting (see the
  "Write apply timing" table in `docs/PROTOCOL.md`).
- **Verify the real service, not the config field** (`:502` for Modbus; registration for
  2030.5). A changed flag is not proof the service changed.
- Rule: after a write, poll and confirm the observable behaviour. If it can't be
  confirmed within the window, say so (and whether a reboot is needed) — do not report
  success.
- **Never reboot to "apply" a setting unattended** — a reboot can strand the aGate on 4G
  (no auto-WiFi-reconnect). See R6 and `DEF-WIFI-RECONNECT`.

## R3 — Record prior state before any device write

Snapshot the full prior block (and any coupled state) before writing, log it, and make it
revertible. Return it to the caller (e.g. `prior_soc`, `prior_der_comms`). Reference:
[AGENT memory: record-prior-state-before-device-writes]. Coupled settings matter — e.g.
reserve SoC is reset by a mode change, so capture both.

## R4 — Health check & re-discovery

A health check MUST report the **actual services** via a real protocol round-trip, not a
ping. The reference is the FranklinWH Modbus Bridge UI: `Test OK 16.6ms`, `9000:ok
502:ok Modbus:ok`, `Polling`.

- **The authoritative check is a real sendMqtt round-trip WITH retries** (login, or a read
  like `power_flow`), and report its **latency** (`Test OK 16.6ms`). Retries are essential:
  the local WiFi link is often lossy, and a round-trip with retries succeeds where single
  probes drop.
- **Ping is INFORMATIONAL only — never short-circuit on a failed ping.** On a lossy link a
  single ICMP packet frequently drops even though the aGate is fully reachable (observed:
  87% packet loss, yet `call 1205` succeeded). Report the ping result, but base the verdict
  on the protocol round-trip. `discover.ping()` returns `True`/`False`/`None`.
- **`:502`** (Modbus): best-effort TCP check, a few attempts to ride out packet loss (this
  repo can't do a Modbus protocol handshake — that's `franklinwh-modbus`).
- **der_comms** config (`sunsMdEn`) — compare the config flag against the actual `:502`
  service; flag them when they disagree (see R2).
- A port being open is not enough — non-aGate devices also listen on `9000`; require the
  login handshake to confirm identity.
- The `franklinwh-local health` command implements this.

**The aGate has multiple network interfaces** (eth0, eth1, WiFi, **4G/cellular** — see
cmdType `1119` network_switches / `1117` network_interfaces) and **can fail over to 4G
after a reboot**, leaving the LAN entirely. Observed: a reboot took `192.0.2.110` off
the network and the aGate came up on **4G** — the local API is then **unreachable by
design** (sendMqtt/Modbus are LAN-only; on 4G it is cloud-reachable only). Recovery: it
must rejoin WiFi/ethernet (via the app's network settings, or on its own). A failed
local health check does **not** mean the aGate is down — it may just be off-LAN on 4G.

**Re-discovery:** the aGate **can also come back on a different IP after a reboot**
(observed: `.110` → gone; DHCP re-lease). Do not assume a fixed IP. Provide/point to
discovery:

- `franklinwh-local scan <subnet>` — TCP probe (confirms via login, filtering false
  positives from other :9000 listeners).
- **mDNS** — `franklinwh-modbus` owns the mDNS/service-discovery utilities; find the aGate
  by service identity (robust to IP changes and false-positive ports). Reference those
  utilities rather than duplicating them here.

## R5 — Connectivity resilience

The local WiFi link is often slow/flaky. Transport MUST tolerate it:

- Generous default timeout (`DEFAULT_TIMEOUT`) and **reconnect-retries** on connect,
  request, and **login** (login is the entry point — if it isn't resilient, retry never
  helps). Configurable via `--timeout` / `--retries`.
- On transient drops, reconnect (re-login if needed) and retry. aGate requests are
  idempotent set-to-value ops, so a retry cannot double-apply.

## R6 — Reboot verification (down → up)

There is **no uptime/boot counter** exposed by the device. So a reboot is only *proven* by
the connection lifecycle: `:9000` must go **DOWN** (the aGate actually went offline) and
then come back **UP + accept a login**. If `:9000` never drops, report the reboot had **no
effect** — do not claim success. (`reboot --wait` implements this two-phase check with
progress output.)

## R7 — User-facing behaviour

- **No raw tracebacks** for connection/protocol failures. Catch `(OSError, TransportError,
  TimeoutError)`, print a clean `error: …` line, and add a hint (e.g. run `health` or
  `scan`). Return a non-zero exit code.
- **Destructive/impactful writes require confirmation.** Reboot and 2030.5-enable prompt
  "are you sure?" and support `--force`. Enabling IEEE 2030.5 warns it can hand dispatch to
  a utility/DERMS.
- **Long waits show progress** (elapsed + rough %), not silence.
- **No emoji / icon glyphs in code or output** — plain ASCII only (`UP`/`DOWN`,
  `WARNING:`), not check-marks or symbols.

## R8 — Naming & scope

- cmdType names/descriptions describe the **setting**, not a standard/region. Device field
  names (the raw JSON keys, e.g. `*_AS`) are kept verbatim — they are the device's own keys,
  not our labels.
- This repo is **sendMqtt-local only**. Modbus/SunSpec is `franklinwh-modbus`; cloud REST is
  `franklinwh-cloud`. Do not write into sibling repos (see AGENT.md scope rule).

---

### Quick checklist for a new live write command
1. Read the full block; overlay only changed fields; write full block `opt:1` (R1).
2. Snapshot + log prior state; make it revertible (R3).
3. Re-read and verify the real effect/service; raise on silent discard / mismatch (R2).
4. Confirm before destructive/impactful actions; `--force` to skip (R7).
5. Clean errors, no tracebacks, no emoji (R7).
