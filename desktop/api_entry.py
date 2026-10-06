"""Frozen/dev entry that runs uvicorn for the packaged desktop app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if getattr(sys, "frozen", False):
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

import server.main  # noqa: F401  # PyInstaller follows this import
from server.settings import listen_host, listen_port


def _ensure_stdio():
    """A windowed PyInstaller exe has no console, so stdout and stderr are None."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main():
    import uvicorn

    _ensure_stdio()
    uvicorn.run("server.main:app", host=listen_host(), port=listen_port(), log_level="info")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
