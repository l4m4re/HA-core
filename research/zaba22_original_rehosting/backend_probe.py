from __future__ import annotations

import json

from .harness import backend_availability


def main() -> None:
    print(json.dumps(backend_availability(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
