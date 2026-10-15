# API Reference

Auto-generated from the source docstrings. Everything below is importable from
the top-level package, e.g. `from franklinwh_direct_connect_api import LocalClient`.

---

## High-level client

The friendliest entry point: connect, log in, call named reads.

::: franklinwh_direct_connect_api.client.LocalClient

---

## Transport

Lower-level framed TCP client (login + request/response, full `Frame` objects).

::: franklinwh_direct_connect_api.transport.LocalTransport

::: franklinwh_direct_connect_api.transport.TransportError

---

## Protocol

Cipher, frame encode/decode, the streaming reader, and the pcap reader.

::: franklinwh_direct_connect_api.protocol.Frame

::: franklinwh_direct_connect_api.protocol.encode_frame

::: franklinwh_direct_connect_api.protocol.decode_frame

::: franklinwh_direct_connect_api.protocol.detect_seed

::: franklinwh_direct_connect_api.protocol.FrameStream

::: franklinwh_direct_connect_api.protocol.iter_pcap_frames

---

## Command catalog

::: franklinwh_direct_connect_api.catalog.Cmd

::: franklinwh_direct_connect_api.catalog.CmdInfo

::: franklinwh_direct_connect_api.catalog.describe

::: franklinwh_direct_connect_api.catalog.response_for

::: franklinwh_direct_connect_api.catalog.run_status_desc

::: franklinwh_direct_connect_api.catalog.mode_label

Also exported from the top level, as plain data rather than functions:
`WRITES` (the write table — cmdType, `opt`, fields and how each was confirmed),
`RUN_STATUS` (see the caveat in [PROTOCOL.md](PROTOCOL.md#power_flow-1301-run_status-vs-mode-dont-confuse-them)),
`OPERATING_MODES`, `WORK_MODE_NAMES` and `CATALOG` itself.

---

## Energy history, rollups and TOU

Stateless helpers over `1303` / `1407` payload dicts — sampling and persistence stay with
the caller. See [Energy history and rollups](USAGE.md#energy-history-and-rollups).

::: franklinwh_direct_connect_api.energy.has_data

::: franklinwh_direct_connect_api.energy.period_range

::: franklinwh_direct_connect_api.energy.Rollup

::: franklinwh_direct_connect_api.energy.aggregate

::: franklinwh_direct_connect_api.energy.rollup

::: franklinwh_direct_connect_api.energy.TouBlock

::: franklinwh_direct_connect_api.energy.decode_tou

::: franklinwh_direct_connect_api.energy.active_tier

::: franklinwh_direct_connect_api.energy.tier_transitions

---

## Probing for undocumented cmdTypes

Read-only sweep machinery behind `franklinwh-direct-connect probe` — see
[Probing](USAGE.md#probing-for-undocumented-cmdtypes).

::: franklinwh_direct_connect_api.probe.ProbeResult

::: franklinwh_direct_connect_api.probe.default_payloads

::: franklinwh_direct_connect_api.probe.expand_payloads

::: franklinwh_direct_connect_api.probe.discover_serials

::: franklinwh_direct_connect_api.probe.gap_codes

::: franklinwh_direct_connect_api.probe.probe_codes

::: franklinwh_direct_connect_api.probe.find_cell_series

---

## Discovery (LAN scan)

::: franklinwh_direct_connect_api.discover.scan

::: franklinwh_direct_connect_api.discover.HostResult

::: franklinwh_direct_connect_api.discover.expand_targets

::: franklinwh_direct_connect_api.discover.default_gateway

::: franklinwh_direct_connect_api.discover.probe_sendmqtt

::: franklinwh_direct_connect_api.discover.probe_modbus

---

## Emulator

::: franklinwh_direct_connect_api.emulator.Emulator

The emulator synthesises responses from a deterministic site model; it is a development
and test aid, **not** evidence of real device behaviour. See
[Test without hardware](USAGE.md#test-without-hardware-emulator).

---

## Decoding proxy

Exported at the top level as `proxy_serve` and `log_frame`.

::: franklinwh_direct_connect_api.proxy.serve

::: franklinwh_direct_connect_api.proxy.log_frame
