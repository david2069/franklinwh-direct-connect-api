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
    any particular purpose**. Any use — personal or commercial — is permitted under the MIT License and is
    entirely at your own risk. The author(s) and contributor(s) accept
    **no responsibility or liability** for any consequences of its use — data loss, equipment damage, or
    otherwise.

    **By using this library, you acknowledge that:**

    - You are accessing an interface not intended for your use
    - The protocol may change or become unavailable at any time
    - You assume all risk associated with its use
    - You will use it responsibly and keep your gateway/grid settings compliant with the official FranklinWH
      app and installer configuration

    **Compliance & anti-circumvention.** FranklinWH-managed settings may exist to, among other things:

    - protect the **safety and longevity** of the battery and gateway;
    - apply **automatic software updates**, and restrict your ability to view or change battery,
      grid-import or grid-export controls;
    - enforce your **local grid profile** and any import/export limits or prohibitions;
    - enforce restrictions tied to **contractual incentives, subsidies, or VPP/grid programmes**.

    Using this software to bypass or override any such control, restriction or compliance measure —
    deliberately or inadvertently — is **entirely at your own risk**, and is neither condoned nor
    encouraged by the authors or any other party.

    **Do NOT contact FranklinWH support** about this software — raise issues on GitHub:
    <https://github.com/david2069/franklinwh-direct-connect-api/issues>.

    **MIT License**, plus
    [Additional Terms](https://github.com/david2069/franklinwh-direct-connect-api/blob/main/LICENSE)
    — the authoritative text.

## Why this exists

The cloud REST API drops most structural telemetry (battery cell voltages, relay
states, full physics arrays) to speed up the mobile app. That data still flows
over the local broker channel. `franklinwh-direct-connect` speaks it directly.

## Where to go next

<div class="grid cards" markdown>

- :material-rocket-launch: **[Usage Guide](USAGE.md)** — install, connect via the
  hotspot, CLI, library API, emulator, decoding captures.
- :material-protocol: **[Protocol & Catalog](PROTOCOL.md)** — wire format, the
  cipher, the `cmdType` catalog, and what each write is verified against.
- :material-api: **[API Reference](API.md)** — auto-generated from the source
  docstrings.
- :material-scale-balance: **[Compare: the two Local API libraries](LOCAL_API_COMPARISON.md)** — this library vs `voidstarr/franklinwh_local`.

</div>

## 30-second taste

```bash
pip install franklinwh-direct-connect-api
```

No aGate to hand? Run the emulator and point any of this at `127.0.0.1` instead — only
the two lines marked *live* need real hardware.

```python
from franklinwh_direct_connect_api import DirectConnectClient

with DirectConnectClient("10.100.1.1") as c:   # the hotspot gateway IP
    c.login()
    flow = c.power_flow()
    print(f"SoC {flow['soc']}%  load {flow['p_load']}W  battery {flow['p_fhp']}W")
```

```bash
franklinwh-direct-connect emulate --port 9000             # no hardware: a fake aGate
franklinwh-direct-connect --host 127.0.0.1 power_flow     # ... talk to it

franklinwh-direct-connect scan gateway                    # live: find the aGate on its hotspot
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 5   # live
```

`DirectConnectClient` is the name from 0.4.0 on; `LocalClient` is kept as an alias of
the same class.

!!! note "Security"
    The channel is plain TCP with keyless obfuscation. Anyone on the hotspot can
    read or forge frames, and payloads include WiFi credentials and location.
    Use only on networks you control.
