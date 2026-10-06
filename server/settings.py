"""Server settings. Mapping/uk live here, not in vay.reports. Defaults come from .env."""

import os
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env", override=False)
load_dotenv(_ROOT / ".env.example", override=False)

SESSION_COOKIE = "vay_session"
SOURCE_TYPES = ("sales", "receipt", "credit_note", "arr", "items", "stock", "payments", "party", "customer")
EVENT_TYPES = ("sales", "receipt", "credit_note", "items", "payments")
SNAPSHOT_TYPES = ("arr", "stock", "party", "customer")
DATE_FIELDS = {"Date"}
AMOUNT_FIELDS = {
    "Net Amount", "Amount", "Sales Amount", "SGST", "CGST", "IGST",
    "Qty", "Balance", "Days", "P.Price", "Rate",
}
NAME_FIELDS = ("Party Name", "Account Name", "Item Name")
UK_SEP = "\x1f"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
ROW_PAGE_DEFAULT = 50
ROW_PAGE_CAP = 200

PACK_PHASES = {
    "core": ["core"],
    "fiscal": ["fiscal"],
    "items": ["items"],
    "profit": ["profit", "expenses", "itemprofit"],
}

PACK_TYPES = {
    "core": ["sales", "receipt", "credit_note", "arr"],
    "fiscal": ["sales", "receipt", "credit_note", "arr"],
    "items": ["items", "stock"],
    "profit": ["sales", "credit_note", "payments", "items", "stock"],
}

SALES_SAME_AMOUNT_UK = {"Date", "Party Name", "Sales Rep", "Net Amount"}

REQUIRED_FIELDS = {
    "sales": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    "receipt": ["Date", "Account Name", "Sales Rep", "Amount"],
    "credit_note": ["Date", "Party Name", "Invoice No", "Net Amount"],
    "arr": ["Account Name", "Group", "Balance"],
    "items": ["Date", "Item Name", "Qty", "Rate"],
    "stock": ["Item Name", "Qty", "P.Price"],
    "payments": ["Date", "Account Name", "Amount"],
    "party": ["Account Name", "Group"],
    "customer": ["Account Name", "Group", "Balance"],
}

# Stock columns. Empty is allowed, so they are not required and a file without them still imports.
# Stored on the stock row when that file maps them, and on item_attr for the 360 views.
ITEM_ATTR_FIELDS = ("Category", "Item Group", "Brand", "Supplier")

DEFAULT_UNIQUE_KEYS = {
    "sales": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    "receipt": ["Date", "Account Name", "Sales Rep", "Amount"],
    "credit_note": ["Date", "Party Name", "Invoice No", "Net Amount"],
    "arr": ["Account Name"],
    "items": ["Date", "Item Name", "Qty", "Rate"],
    "stock": ["Item Name"],
    "payments": ["Date", "Account Name", "Amount"],
    "party": ["Account Name"],
    "customer": ["Account Name"],
}

TYPE_LABELS = {
    "sales": "Sales",
    "receipt": "Receipts",
    "credit_note": "Credit notes",
    "arr": "Outstanding",
    "items": "Item-wise sales",
    "stock": "Stock",
    "payments": "Payments",
    "party": "Parties",
    "customer": "Customers",
}

CLEANUP_TYPES = ("arr", "sales", "items", "payments", "receipt", "credit_note", "stock")


def mongo_uri():
    return (os.environ.get("MONGODB_URI") or "").strip()


def use_memory_store():
    return os.environ.get("VAY_STORE") == "memory"


def sync_jobs():
    return os.environ.get("VAY_SYNC_JOBS") == "1"


def cors_origins():
    raw = (os.environ.get("VAY_CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def cookie_secure():
    """Set VAY_COOKIE_SECURE=1 when serving over HTTPS so session cookies require TLS."""
    return (os.environ.get("VAY_COOKIE_SECURE") or "").strip().lower() in ("1", "true", "yes")


def login_rate_limit():
    try:
        return max(1, int(os.environ.get("VAY_LOGIN_RATE_LIMIT") or "10"))
    except ValueError:
        return 10


def login_rate_window_sec():
    try:
        return max(30, int(os.environ.get("VAY_LOGIN_RATE_WINDOW") or "300"))
    except ValueError:
        return 300


def listen_host():
    return (os.environ.get("VAY_HOST") or "0.0.0.0").strip() or "0.0.0.0"


def listen_port():
    try:
        return int(os.environ.get("VAY_PORT") or "8765")
    except ValueError:
        return 8765


def data_dir():
    raw = (os.environ.get("VAY_DATA_DIR") or "").strip()
    if raw:
        return Path(raw)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Vay Reports"
    return Path.home() / ".vay-reports"


def web_dist():
    if getattr(sys, "frozen", False):
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "web" / "dist")
        candidates.append(Path(sys.executable).resolve().parent / "web" / "dist")
        for path in candidates:
            if (path / "index.html").is_file():
                return path
        return candidates[0]
    return _ROOT / "web" / "dist"


def lan_ips():
    found = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.3)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not str(ip).startswith("127."):
            found.append(ip)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip and not str(ip).startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def export_dir():
    raw = (os.environ.get("VAY_EXPORT_DIR") or "").strip()
    if raw:
        return Path(raw)
    if os.environ.get("VAY_DATA_DIR"):
        return data_dir() / "exports"
    return _ROOT / "vay_reports"
