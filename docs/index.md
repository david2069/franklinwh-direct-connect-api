# FranklinWH Direct Connect

Unofficial Python library and CLI for the FranklinWH aGate **local broker
protocol** — the JSON `cmdType` frames exchanged over **TCP/9000**, the local
interface the official FranklinWH app calls **"Direct Connect."** This is the
lower-level device↔broker channel that the cloud `sendMqtt` REST relay (see
[`franklinwh-cloud`](https://github.com/david2069/franklinwh-cloud)) sits on top of.

!!! warning "Status: alpha"
    Reverse-engineered from packet captures. Frame parsing/encoding and the
    offline tooling are well tested; live transport against real hardware should
    be validated on your own LAN.

!!! danger "Important Disclaimer"
    This library is **unofficial** and **not endorsed, supported, or affiliated with FranklinWH** in any way.
    It speaks FranklinWH's **undocumented** aGate Direct Connect (local broker) protocol, reverse-engineered
    from packet captures — it may change, break, or become unavailable without notice.

    It is provided **"AS IS"**, for **informational and educational purposes**, without warranty of any
    kind, express or implied, including but not limited to warranties of merchantability or **fitness for
    any particular purpose**. Any use — personal or commercial — is permitted under the MIT Licence and is
    entirely at your own risk. The author(s) and contributor(s) accept
    **no responsibility or liability** for any consequences of its use — data loss, equipment damage, or
    otherwise.

    **By using this library, you acknowledge that:**

    - You are accessing an interface not intended for your use
    - The protocol may change or become unavailable at any time
    - You assume all risk associated with its use
    - You will use it responsibly and keep your gateway/grid settings compliant with the official FranklinWH
      app and installer configuration

    **Do NOT contact FranklinWH support** about this software — raise issues on GitHub:
    <https://github.com/david2069/franklinwh-direct-connect-api/issues>. **MIT Licence.**

## Why this exists

The cloud REST API drops most structural telemetry (battery cell voltages, relay
states, full physics arrays) to speed up the mobile app. That data still flows
over the local broker channel. `franklinwh-local` speaks it directly.

## Where to go next

<div class="grid cards" markdown>

- :material-rocket-launch: **[Usage Guide](USAGE.md)** — install, connect via the
  hotspot, CLI, library API, emulator, decoding captures.
- :material-protocol: **[Protocol & Catalog](PROTOCOL.md)** — wire format, the
  cipher, and the full `cmdType` command catalog.
- :material-api: **[API Reference](API.md)** — auto-generated from the source
- :material-scale-balance: **[Compare: the two Local API libraries](LOCAL_API_COMPARISON.md)** — this library vs `voidstarr/franklinwh_local`.
  docstrings.

</div>

## 30-second taste

```python
from franklinwh_local import LocalClient

with LocalClient("10.100.1.1") as c:   # the hotspot gateway IP
    c.login()
    flow = c.power_flow()
    print(f"SoC {flow['soc']}%  load {flow['p_load']}W  battery {flow['p_fhp']}W")
```

```bash
franklinwh-local scan gateway                    # find the aGate on its hotspot
franklinwh-local --host 10.100.1.1 power_flow --watch 5
franklinwh-local emulate --port 9000             # test with no hardware
```

!!! note "Security"
    The channel is plain TCP with keyless obfuscation. Anyone on the hotspot can
    read or forge frames, and payloads include WiFi credentials and location.
    Use only on networks you control.
