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
