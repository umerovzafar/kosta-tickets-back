"""Запуск скриптов мок-данных Time Tracking из корня репозитория `tickets-back`.

Не требует `cd time_tracking` и `PYTHONPATH`: подставляется автоматически.

Примеры::

  python mock_data.py --help
  python mock_data.py seed --weeks 8
  python mock_data.py delete
  python mock_data.py delete --apply
  python mock_data.py reset --weeks 10
  python mock_data.py reset --skip-expenses

Сервер (Docker, каталог ``/app``): скопируйте только каталог ``time_tracking/scripts`` в образ
или вызывайте ``python scripts/tt_mock_data.py`` (см. `time_tracking/scripts/tt_mock_data.py`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_TT = _ROOT / "time_tracking"
_SCR = _TT / "scripts" / "tt_mock_data.py"


def main() -> None:
    if not _SCR.is_file():
        print("Не найден:", _SCR, file=sys.stderr)
        raise SystemExit(1)
    env = {**os.environ, "PYTHONPATH": str(_TT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")}
    r = subprocess.run([sys.executable, str(_SCR), *sys.argv[1:]], cwd=str(_TT), env=env)
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
