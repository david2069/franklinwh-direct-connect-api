"""``python -m franklinwh_local`` — deprecated; use ``franklinwh_direct_connect_api``."""
from franklinwh_direct_connect_api.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
