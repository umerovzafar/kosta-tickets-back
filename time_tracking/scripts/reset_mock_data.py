"""Полный цикл: ``delete_mock_data --apply``, затем ``seed_mock_data`` с теми же аргументами (кроме delete-only).

Все аргументы командной строки (кроме исполняемого файла) передаются **в сид**; в удаление
добавляются только ``--apply`` и, при необходимости, ``--skip-expenses`` (если оно есть среди аргументов).

Пример::

  python scripts/reset_mock_data.py
  python scripts/reset_mock_data.py --weeks 12
  python scripts/reset_mock_data.py --skip-expenses --no-exchange-table
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_APP = _HERE.parent


def main() -> None:
    os.chdir(_APP)
    if str(_APP) not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        os.environ["PYTHONPATH"] = str(_APP) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")

    seed_args = list(sys.argv[1:])
    delete_args = ["--apply"]
    if "--skip-expenses" in seed_args:
        delete_args.append("--skip-expenses")

    py = sys.executable
    d_cmd = [py, str(_HERE / "delete_mock_data.py"), *delete_args]
    s_cmd = [py, str(_HERE / "seed_mock_data.py"), *seed_args]

    print("→", " ".join(d_cmd), file=sys.stderr)
    r1 = subprocess.run(d_cmd, cwd=_APP, env={**os.environ})
    if r1.returncode != 0:
        sys.exit(r1.returncode)
    print("→", " ".join(s_cmd), file=sys.stderr)
    r2 = subprocess.run(s_cmd, cwd=_APP, env={**os.environ})
    if r2.returncode != 0:
        sys.exit(r2.returncode)
    print("Готово: мок-данные пересозданы.", file=sys.stderr)


if __name__ == "__main__":
    main()
