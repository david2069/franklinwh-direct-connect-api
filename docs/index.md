# FranklinWH Direct Connect

This library is a **proof-of-concept demonstration** of how to talk to a FranklinWH
aGate over the (undocumented, unofficial) **FranklinWH Direct Connect** local API —
the JSON `cmdType` frames exchanged over **TCP/9000**. It is the lower-level
device↔broker channel that the cloud `sendMqtt` REST relay (see
[`franklinwh-cloud`](https://github.com/david2069/franklinwh-cloud)) sits on top of.

!!! info "On the names"
    *Direct Connect* is FranklinWH's own term for the gateway's local protocol. This
    project implements it, and is the **library and CLI** — not an application. The
    [Direct Connect Bridge](https://github.com/david2069/franklinwh-direct-connect-bridge)
    is the application built on top of it, and is where a REST API, MQTT, Home Assistant
    entities and a web UI live. Using FranklinWH's term implies **no affiliation with,
    endorsement by, or support from FranklinWH**.

    The PyPI distribution is `franklinwh-direct-connect-api`, the import package is
    `franklinwh_direct_connect_api`, and the CLI is `franklinwh-direct-connect`. The
    pre-0.4.0 spellings still work, because removing them would break existing code —
    `franklinwh_local` returns the *same* module objects, `franklinwh-local` is the same
    entry point, and `LocalClient`/`LocalTransport` remain class aliases.

!!! warning "Not for production, and compatibility is not guaranteed"
    **There is no guarantee this is compatible with your FranklinWH gateway(s),
    aPower(s) or connectivity — now or in the future.** FranklinWH
    ***<u>may change, block or deprecate this interface at any time</u>***.

    Tested on a LAN against **one** aGate X with **one** aPower, most recently on
    `IBG_VER V12R02B60D00_260924` / `protocolVer V1.12.02` (read 2026-10-31). One site
    on one firmware is a hypothesis, not a compatibility matrix — **multi-aPower
    behaviour is unobserved**, and anything marked UNCONFIRMED has not been proven on
    any hardware.

!!! danger "TCP 9000 is a reserved port"
    This library's emulator **refuses to start on TCP 9000** and defaults to **19000**.
    `9000` belongs to a real aGate and to the **FranklinWH Gateway Emulator** — the
    official emulator, which is deliberately *transparent*, so something answering on
    9000 is meant to be indistinguishable from a gateway. This library's mock must stay
    distinguishable from one: a mock left on 9000 once appeared in a LAN scan as
    `9000/sendMqtt CONFIRMED`, which makes every discovery result untrustworthy.

!!! tip "No gateway? Run the emulator first"
    A deterministic synthetic aGate with N aPowers — live telemetry, energy history,
    smart circuits, and writes that persist — so you can see the whole thing work before
    connecting real hardware. It is a development aid: it serves what it was told to
    serve, so it is **not** evidence of how real hardware behaves.

!!! warning "Status: alpha"
    Reverse-engineered from packet captures. Frame parsing/encoding and the
    offline tooling are well tested; live transport against real hardware should
    be validated on your own LAN.

!!! danger "Important Disclaimer"
    This library is **unofficial** and **not endorsed, supported, or affiliated with FranklinWH** in any way.
    It speaks FranklinWH's **undocumented** aGate Direct Connect (local broker) protocol, reverse-engineered
    from packet captures.
    It ***<u>may change, break, or become unavailable without notice</u>***.

    It is provided **"AS IS"**, for **informational and educational purposes**, without warranty of any
    kind, express or implied, including but not limited to warranties of merchantability or **fitness for
    any particular purpose**. Any use — personal or commercial — is permitted under the MIT License and is
    entirely at your own risk. The author(s) and contributor(s) accept
    **no responsibility or liability** for any consequences of its use — data loss, equipment damage, or
    otherwise.

    **By using this library, you acknowledge that:**

    - You are accessing an interface not intended for your use
    - The protocol ***<u>may change or become unavailable at any time</u>***
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
franklinwh-direct-connect emulate                         # no hardware: a fake aGate
franklinwh-direct-connect --host 127.0.0.1 --port 19000 power_flow   # ... talk to it

franklinwh-direct-connect scan gateway                    # live: find the aGate on its hotspot
franklinwh-direct-connect --host 10.100.1.1 power_flow --watch 5   # live
```

`DirectConnectClient` is the name from 0.4.0 on; `LocalClient` is kept as an alias of
the same class.

!!! note "Security"
    The channel is plain TCP with keyless obfuscation. Anyone on the hotspot can
    read or forge frames, and payloads include WiFi credentials and location.
    Use only on networks you control.
