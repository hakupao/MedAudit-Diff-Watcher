from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    try:
        from medaudit_diff_watcher.gui_qt_app import main as qt_main
    except ImportError as exc:
        print(
            "PySide6 is required for the GUI. Install with `python -m pip install -e .[gui]` (or include PySide6 in your environment).",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return 1
    return int(qt_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
