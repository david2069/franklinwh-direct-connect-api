# API Reference

Auto-generated from the source docstrings. Everything below is importable from
the top-level package, e.g. `from franklinwh_local import LocalClient`.

---

## High-level client

The friendliest entry point: connect, log in, call named reads.

::: franklinwh_local.client.LocalClient

---

## Transport

Lower-level framed TCP client (login + request/response, full `Frame` objects).

::: franklinwh_local.transport.LocalTransport

::: franklinwh_local.transport.TransportError

---

## Protocol

Cipher, frame encode/decode, the streaming reader, and the pcap reader.

::: franklinwh_local.protocol.Frame

::: franklinwh_local.protocol.encode_frame

::: franklinwh_local.protocol.decode_frame

::: franklinwh_local.protocol.detect_seed

::: franklinwh_local.protocol.FrameStream

::: franklinwh_local.protocol.iter_pcap_frames

---

## Command catalog

::: franklinwh_local.catalog.Cmd

::: franklinwh_local.catalog.CmdInfo

::: franklinwh_local.catalog.describe

::: franklinwh_local.catalog.response_for

---

## Discovery (LAN scan)

::: franklinwh_local.discover.scan

::: franklinwh_local.discover.HostResult

::: franklinwh_local.discover.expand_targets

::: franklinwh_local.discover.default_gateway

::: franklinwh_local.discover.probe_sendmqtt

::: franklinwh_local.discover.probe_modbus

---

## Emulator

::: franklinwh_local.emulator.Emulator
