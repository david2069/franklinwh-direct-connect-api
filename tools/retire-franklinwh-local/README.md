# franklinwh-local — renamed

This distribution is **retired**. It was only ever published as `0.1.0a0`, a pre-release,
so `pip install franklinwh-local` never resolved it without `--pre`.

The project is now:

```bash
pip install franklinwh-direct-connect-api
```

```python
from franklinwh_direct_connect_api import DirectConnectClient
```

**Direct Connect** is FranklinWH's own term for the aGate's local protocol, so the library
was renamed to match it.

Installing this package pulls in `franklinwh-direct-connect-api` for you. It contains no
modules of its own — the old `franklinwh_local` import name is provided by that package as
a deprecated alias, and is removed in its 0.5.0.

- Repository: https://github.com/david2069/franklinwh-direct-connect-api
- Documentation: https://david2069.github.io/franklinwh-direct-connect-api/
