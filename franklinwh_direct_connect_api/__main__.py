"""Allow ``python -m franklinwh_local ...`` as an alias for the CLI.

Useful when the ``franklinwh-direct-connect`` console script is not on ``PATH``
(e.g. the virtualenv is installed but not activated).
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
