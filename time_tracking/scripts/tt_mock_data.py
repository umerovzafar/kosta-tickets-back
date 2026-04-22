"""Один скрипт для сида и удаления мок-данных (обёртка над seed_mock_data / delete_mock_data).

Запуск на сервере из корня приложения time tracking (в Docker: ``cd /app``)::

  python scripts/tt_mock_data.py --help
  python scripts/tt_mock_data.py seed --help
  python scripts/tt_mock_data.py delete --help

Примеры::

  python scripts/tt_mock_data.py seed
  python scripts/tt_mock_data.py delete
  python scripts/tt_mock_data.py delete --apply
  python scripts/tt_mock_data.py seed --skip-expenses
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_APP = _SCRIPTS.parent
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "action",
        choices=("seed", "delete"),
        help="seed — добавить мок-данные; delete — удалить (см. --apply у delete)",
    )
    p.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        help="Аргументы для выбранного сценария (через -- ...)",
    )
    args = p.parse_args()
    # allow: tt_mock_data.py seed -- --weeks 4
    rest = list(args.rest)
    if rest and rest[0] == "--":
        rest = rest[1:]

    if args.action == "seed":
        sys.argv = ["seed_mock_data.py", *rest]
        from seed_mock_data import main as run

        run()
    else:
        sys.argv = ["delete_mock_data.py", *rest]
        from delete_mock_data import main as run

        run()


if __name__ == "__main__":
    main()
