# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

spec_dir = Path(SPECPATH).resolve()
if spec_dir.is_file():
    spec_dir = spec_dir.parent
repo = spec_dir.parent
dist_ui = repo / "web" / "dist"

hidden = collect_submodules("uvicorn")
hidden += collect_submodules("server")
hidden += [name for name in collect_submodules("vay") if not name.startswith("vay.ui")]
hidden += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "multipart",
    "dotenv",
    "fpdf",
    "gridfs",
    "pymongo",
    "openpyxl",
    "pandas",
]

datas = collect_data_files("uvicorn")
if (dist_ui / "index.html").is_file():
    datas += [(str(dist_ui), "web/dist")]

a = Analysis(
    [str(spec_dir / "api_entry.py")],
    pathex=[str(repo)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "streamlit",
        "altair",
        "pytest",
        "py",
        "IPython",
        "matplotlib",
        "tkinter",
        "tensorflow",
        "torch",
        "notebook",
        "jupyter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vay-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=sys.platform != "win32",
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="vay-api",
)
