# Vay Reports

**Vay Reports** (v3.0.0) is a desktop- and LAN-friendly reporting product for businesses that export Excel workbooks from **AppSheet**. It ports the reporting logic of Google Apps Script `Vay_Reports_Fixed.gs` into a Python engine, then wraps it in a React + FastAPI + MongoDB product UI.

You import sales, receipts, outstanding (ARR), items, stock, payments, and related sheets; map columns once; store rows in MongoDB; then generate official report packs for **one report date** over **all stored rows**.

> **Important:** Explorer filters on Sales, Finance, and Stock do **not** change official Create numbers. Official reports always use the full stored dataset plus the report date you choose.

---

## What it does

Reporting conventions inherited from the Apps Script engine include MTD, last 15 days, rolling months, YTD (1 Apr → report date), fiscal-year slices, and settlement aging (oldest-first receipts by default).

There is **no live AppSheet API**. The workflow is always: **export Excel from AppSheet → import into Vay Reports**.

For the full catalogue of product capabilities, see **[Available features](#available-features)** below.

Phase 0 product definition (buyers, pilots, shared model, org policy) lives in **[`docs/phase0/`](docs/phase0/)**. Expense category account names are seeded from the `vay_wholesale` pack into Organization settings — they are not hard-coded in report formula modules.

Phase 1 gate support: import provenance (`file_sha256`, mapper versions, row counts), import modes (`skip` / `update` / `replace_batch` / `replace_period`) with dry-run preview and undo, reconciliation via `*.recon.json` sidecars (`POST /api/recon/sidecars`), and Create run **manifests** (“Why these numbers?”) including data/calculation versions.

---

## Architecture

```text
AppSheet Excel export
        │
        ▼
 Import + column mappers  ──►  MongoDB
        │                      (rows, uploads/GridFS, runs, users, roles, settings)
        ▼
 POST /api/runs  ──►  background job  ──►  vay.engine.generate(...)
        │                                         │
        ▼                                         ▼
 Run snapshot (report tables)              Optional Excel / PDF zip
        │
        ▼
 React UI (dashboard, 360, finance, report families)
```

| Layer | Role |
|-------|------|
| **`vay/`** | Pure report engine (shared by API jobs, Streamlit, and golden tests) |
| **`server/`** | FastAPI: auth, uploads, mappers, runs, views, settings, PDF export |
| **`web/`** | React SPA (Vite). Dev proxies `/api`; production is served by FastAPI from `web/dist` |
| **`desktop/`** | Electron shell — full app (bundled Mongo + API) or thin client (UI → remote URL) |
| **`app.py`** | Streamlit UI for **engine development only** (does not write back to AppSheet) |
| **`Vay_Reports_Fixed.gs`** | Original Apps Script reference |

---

## Repository layout

```text
vay-appsheet-report/
├── server/           # FastAPI application
├── vay/              # Report engine (pandas / openpyxl)
│   └── reports/      # core, fiscal, items, profit
├── web/              # React + Vite frontend
├── desktop/          # Electron + PyInstaller packaging
├── scripts/          # build-desktop.ps1/.sh, make_engine_golden.py
├── tests/            # pytest + gs_golden fixtures
├── app.py            # Streamlit engine-dev UI
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Tech stack

| Area | Stack |
|------|--------|
| Frontend | React 18, Vite 5, Recharts |
| Backend | FastAPI, Uvicorn, bcrypt, python-multipart |
| Engine | Python 3.12+, pandas, openpyxl, python-dateutil |
| PDF | fpdf2 |
| Database | MongoDB 7 (+ GridFS); in-memory store for tests |
| Desktop | Electron 33, electron-builder (NSIS, DMG, PKG), bundled `mongod`, PyInstaller `vay-api` |
| CI | GitHub Actions — pytest + web build |
| Containers | Docker multi-stage (Node 20 → Python 3.12) |

---

## Available features

### Product navigation map

| Menu | Screens |
|------|---------|
| **Home** | Dashboard |
| **Data** | Import · Explore · Export (PDF) · Excel |
| **Sales** | Sales invoices · Item-wise sales |
| **360 View** | Customers · Items · Customer group · Sales rep |
| **Finance** | Parties · Outstanding · Receipts · Payments |
| **Stock** | Stock |
| **Reports** | Create · Performance · Follow-up · Monthly · Items · Profit · Data issues |
| **Settings** | Network · Organization · Settlement · Due days · Order check · Party types · Advanced · Users · Roles |

Navigation is permission-filtered: users only see screens their role allows. Report families stay disabled until a successful Create has produced that family.

---

### Home — Dashboard

- Greeting and quick actions (Import / Create when relevant)
- **Official snapshot** for the selected run: MTD, last 15 days, and YTD sales vs collection (gap and collection rate)
- **Total sales / collection** when available from the run
- **AR & aging tiles**: outstanding due, AR balance, DSO, configurable aging bands (0–15 … 90+), 30+ days overdue
- **Attention lists**: customers needing follow-up / urgent; stock to refill
- Charts: sales vs collection by period; aging breakdown; monthly trends
- Profit / expense / margin KPIs when the profit pack was run
- Follow-up counts (inactive customers MTD, collection follow-ups)
- Invoice MTD count and average invoice
- Links into 360 View, Finance, Stock, and report families
- **Snapshot picker** (top bar) to switch among succeeded Create runs

---

### Data

#### Import

Multi-step wizard:

1. **File** — Excel or CSV (up to **200 MB**)
2. **Sheets** — Detect sheets and assign types
3. **Preview** — Sample rows before commit
4. **Mapping** — Column map + unique keys (saved per type)
5. **Duplicates** — Resolve conflicts against unique keys
6. **Existing** — Review what is already stored
7. **Import** — Progress for the background import job
8. **Reports** (optional) — Jump into Create with pack selection

Supported import types and required mapped fields:

| Type | Label | Required fields (defaults) |
|------|--------|----------------------------|
| `sales` | Sales | Date, Party Name, Sales Rep, Net Amount |
| `receipt` | Receipts | Date, Account Name, Sales Rep, Amount |
| `arr` | Outstanding | Account Name, Group, Balance |
| `items` | Item-wise sales | Date, Item Name, Qty, Rate |
| `stock` | Stock | Item Name, Qty, P.Price |
| `payments` | Payments | Date, Account Name, Amount |
| `party` | Parties | Account Name, Group |
| `customer` | Customers | (directory / enrichment; mapped separately) |

Also: persistent mappers, unique-key rebuild, and optional Create right after a successful import.

#### Explore

- Query stored rows by type with filters (party, rep, group, item, date range)
- Snapshot types (`arr`, `party`, `stock`) have no date filter
- **Does not** affect official Create numbers

#### Export (PDF)

- After a succeeded run: select report sheets by family and download a **PDF zip**
- Progress polling while the export job runs
- Selection respects permissions (only sheets you can view)

#### Excel

- Download the **permission-filtered workbook** for the current snapshot
- Sheets match the reports you can view; switch snapshot in the top bar for another run

---

### Sales

#### Sales invoices

- Searchable / filterable invoice list (customer, group, salesperson, invoice, date)
- Invoice detail view (deep-link `#/invoice/…`)
- Cross-links to customers, items, and groups where permitted

#### Item-wise sales

- Line-level item sales with filters (customer, group, salesperson, invoice, item, date)
- Links into item and customer 360 profiles

---

### 360 View

Built for the same report date as the selected Create run (Customers / Groups / Reps / Items 360 steps run with every Create).

#### Customers

- Directory: search, filter, sort (including due age); status pills (On track / Follow up / Urgent / Advance)
- **Premium** customer flag
- Profile tabs: **Due** · **Settlements** · **Ordering** · **Order check** · **Activity** · **Years** · **Buying**
- Aging buckets on open AR; settlement history
- **Ordering**: sales flagged as ordered while overdue; CSV export of follow-up rows
- **Order check**: policy-based recommendation (create / reduce / follow up / push back); per-customer overrides for due days and policy
- **Share PDF** (customer or sales-rep oriented)
- Editable **due days** override (when permitted)

#### Customer group

- Group directory and profile with aggregated due / aging / members
- Due-days and order-check overrides at group level
- Member list with salesperson rollup

#### Sales rep

- Rep directory and profile (customers, groups, YTD, last sale, status)
- Due-days and order-check overrides at rep level
- Rollup of ordering / follow-up pressure

#### Items (360)

- Item directory with stock position / status filters
- Item profile: movement, groups, holding levels
- Set **holding** (default and per-item) for refill signalling
- Deep-link `#/item/…`

---

### Finance

Filterable operational tables (filters do **not** change official reports):

| Screen | Notes |
|--------|--------|
| **Parties** | Party list with type, group, balance; party-type filter |
| **Outstanding** | ARR balances by party / group |
| **Receipts** | Dated receipts by party / rep / group |
| **Payments** | Dated payments (feeds expense mapping in profit pack) |

---

### Stock

- Stock list with item, status, and position filters
- Quantities and cost (P.Price); refill signalling vs holding
- Links to Items 360

---

### Reports

#### Create

- Choose packs + **one report date**
- Uses **all stored rows** (not Explorer filters)
- Gated until Settlement setup is complete (`setup_complete`)
- Background job with live step progress by family (including 360 rebuild)
- On success: open families from the Reports menu or switch snapshots from the top bar

#### Report packs → generated sheets

| Pack | UI title | Generated reports (friendly titles) | Family |
|------|----------|-------------------------------------|--------|
| **core** | Sales, collections, and follow-up | Sales by person; Sales by customer; Sales by group | Performance |
| | | Who to follow up — sales; Who to follow up — collections | Follow-up |
| **fiscal** | Month-by-month by year | This year by month — people / customers / groups | Monthly |
| **items** | Items and stock | Item sales; Items missing cost; Item quantity by month | Items |
| **profit** | Profit and expenses | Profit and loss; Expenses by category / account; Unmapped payments; Item profit; Item profit by month | Profit |
| *(with core or items)* | | Data issues (source warnings: missing sheets, future dates, etc.) | Data issues |

Every Create also refreshes **360 View** snapshots (customers, groups, reps, items).

Profit pack access is **permission-gated** (no extra password in the product UI).

#### Report viewers

- Tabular report UI per family with headers/rows from the run snapshot
- Family entries disabled until that family exists on the selected run

---

### Settings

#### Network

- Shows LAN URLs to open the app from other devices
- Copy-to-clipboard; notes API port and that MongoDB stays on the host PC

#### Settlement

- Modes: **Oldest to latest** (opening → oldest invoices → advance) or **Specific** (match invoice, then oldest on remainder)
- Configurable **aging bands** (default 0–15, 15–30, 30–45, 45–60, 60–90, 90+; editable labels / cutoffs)
- Completing settlement marks setup complete so Create is allowed

#### Due days

- Global default credit terms (default 30 days)
- Used by Ordering (ordered while overdue) and Order check (oldest open vs due days)
- Overridable on customer, group, and sales rep

#### Order check

Global policy defaults (also editable under customer / group / rep):

| Section | Controls |
|---------|----------|
| **Credit & due** | Follow-up age, urgent age, overdue grace, credit limit |
| **Order size** | Max order value, max vs avg sale, max vs usual qty, reduce-to usual factor |
| **Frequency & behavior** | Min gap factor, overdue-order ratio, old settlement share |
| **Premium** | Premium limit factor; premium demote option |

Actions surfaced in UI: create order · reduce volume · follow up · push back · strong push back.

#### Party types

- Maintain party-type labels used on the Parties list
- Outstanding imports can tag a party as Customer

#### Advanced

- **Rebuild unique keys** for a chosen data type
- **Clear imported data** by type (outstanding, sales, item-wise, payments, receipts, stock quantities — stock items kept, qty → 0; parties/customers kept; existing report runs kept)
- **Factory reset** — remove imported rows and report runs

#### Users

- List / create / patch / delete users
- Assign roles; enable / disable
- Forced password change on first login when bootstrap default was used

#### Roles

- Create and edit roles
- Fine-grained permissions by group (grant all / clear per group):

| Group | Permissions |
|-------|-------------|
| Sales / Receipts / Outstanding / Payments / Parties / Items / Stock | `view` · `upload` · `map` |
| Customers | `view` |
| Reports | `create` · `view.performance` · `view.followup` · `view.monthly` · `view.items` · `view.profit` · `view.issues` |
| Users / Roles | `view` · `manage` |
| Settings | `import` (any type) · `advanced` |

---

### Auth & security features

- Session cookie `vay_session`
- Bootstrap user **`admin`** (password from `VAY_BOOTSTRAP_PASSWORD` or default `admin123`)
- Optional first-login **must change password**
- Login rate limiting (`VAY_LOGIN_RATE_LIMIT` / `VAY_LOGIN_RATE_WINDOW`)
- CORS allowlist for non-proxied frontends
- `VAY_COOKIE_SECURE=1` for HTTPS deployments
- Permission checks on every API view and on Excel / PDF sheet inclusion

---

### Desktop & deployment features

| Mode | Features |
|------|----------|
| **Full desktop** | Bundled MongoDB + API; system tray (close hides; Quit stops server); LAN serve on `:8765`; splash; NSIS installer on Windows; DMG and PKG on macOS |
| **Thin client** | UI only; configure / change backend URL (`server.json` or `VAY_SERVER_URL`); tray → Change server… |
| **Docker** | Mongo + API; built UI served by FastAPI |
| **Streamlit** | Engine-dev upload → generate → download workbook (no product Mongo persistence) |

---

### Engine / reporting conventions

- Periods: **MTD**, **last 15 days**, rolling months, **YTD** (fiscal year starts **1 April**)
- Settlement aging estimates (opening + oldest-first receipts / invoice application)
- Source-data warnings sheet when core or items packs run
- Excel export with 31-char sheet names and merged fiscal-year headers
- Fiscal golden regression fixtures for engine parity with the original Apps Script logic

---

## Prerequisites

- **Python 3.12+** and `pip`
- **Node.js 20+** and `npm`
- **MongoDB 7** (local or Docker) for product mode — not required for Streamlit engine-dev or `VAY_STORE=memory` tests
- Desktop build: PyInstaller (`desktop/requirements-build.txt`); admin rights for NSIS; on Windows targets, [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist). Mac DMG and PKG installers are built on macOS.

---

## Quick start — product (dev)

1. Copy `.env.example` to `.env` and adjust if needed.
2. Install Python deps and start the API (dev port **8000**):

```text
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8000
```

3. Install and start the web UI (Vite proxies `/api` → `8000`):

```text
cd web
npm install
npm run dev
```

4. Open **http://localhost:5173**, sign in as `admin`, change the password if prompted, complete the setup wizard (Settlement → Import → Create), then map types and upload Excel.

Set `VAY_STORE=memory` **only** for tests (no MongoDB).

---

## Docker

Compose runs MongoDB 7 and the API on port **8765**. The image builds the React UI; FastAPI serves it from `web/dist`.

```text
docker compose up --build
```

- UI + API: **http://localhost:8765**
- Mongo: port **27017** (compose volume `mongo-data`)

---

## Windows desktop (full app)

The packaged app starts:

- Bundled **`mongod`** on `127.0.0.1:27018` (localhost only — not exposed on the LAN)
- **FastAPI** on `0.0.0.0:8765` so other devices on a **trusted LAN** can open the UI in a browser

LAN mode has **no TLS**. Change the bootstrap password on first login. Closing the window hides to the tray; **Quit** stops the server.

### Build the installer

From the repository root:

```text
scripts\build-desktop.ps1
```

On macOS, `scripts/build-desktop.sh` builds the DMG and PKG described below. On other systems it produces the NSIS installer.

These scripts install dependencies, build the web UI and PyInstaller `vay-api`, download MongoDB Community (SSPL), and produce the installer:

**`desktop/release/Vay-Reports-Setup-3.0.0.exe`**

Install with admin rights so the firewall can allow TCP **8765**.

### Local Electron (after web build)

```text
cd web && npm run build
cd desktop
npm run download-mongo
npm start
```

Then open **http://127.0.0.1:8765**, or the LAN address shown on the sign-in page / **Settings → Network**.

Useful desktop scripts: `start` / `dev`, `download-mongo`, `icon`, `dist`, `dist:mac`.

---

## Windows client (UI only)

For PCs that should open the UI **without** running MongoDB or the API. Point them at a machine that already hosts the backend (full desktop, Docker, or `uvicorn`).

```text
cd desktop
npm install
npm run dist:client
```

Output: **`desktop/release/Vay-Reports-Client-Setup-3.0.0.exe`**.

On first launch, enter the backend URL (e.g. `http://192.168.1.10:8765`). It is saved as `server.json` under the user profile. You can also:

- Ship a default in `desktop/client-resources/config.json` before `dist:client`
- Set `VAY_SERVER_URL`
- Use tray → **Change server…** later

Local client run (API must already be up):

```text
cd desktop
npm run start:client
```

---

## macOS desktop

Build on a Mac. An Apple Silicon Mac (including MacBook Air) produces the `arm64` installers. An Intel Mac produces `x64`.

From the repository root:

```text
scripts/build-desktop.sh
```

Or from `desktop/`:

```text
npm run dist:mac
npm run dist:client:mac
```

`dist:mac` is the full app (bundled MongoDB and API). `dist:client:mac` is the UI-only client. Each command writes a DMG and a PKG under `desktop/release/`:

- `Vay-Reports-<version>-<arch>.dmg` and `.pkg`
- `Vay-Reports-Client-<version>-<arch>.dmg` and `.pkg`

The DMG is a drag-into-Applications disk image. The PKG is an installer package. macOS asks to allow incoming connections the first time the full app listens on port **8765**.

---

## Streamlit (engine-dev only)

For iterating on the Python engine without the product stack:

```text
pip install -r requirements.txt
streamlit run app.py
```

Upload Excel → generate → download workbook. This path does **not** persist to the product MongoDB or write back to AppSheet.

---

## Typical user workflow

1. **First run** — Log in as `admin` → change password if required → setup wizard: Settlement → Import → Create  
2. **Settlement** — Choose mode (e.g. oldest-to-latest) and aging bands (`setup_complete` unlocks Create)  
3. **Map & import** — Assign sheet types and columns; handle duplicates; store rows  
4. **Create reports** — Select packs + report date → wait for the job → browse report families  
5. **Operate** — Dashboard, Sales, 360 View, Finance, Stock (filters are exploratory only)  
6. **Export** — PDF zip for a succeeded run  
7. **Admin** — Users / roles; Advanced cleanup or factory reset; Network for LAN URLs  
8. **LAN** — Full desktop on a server PC; browsers or thin clients use `http://<lan-ip>:8765`

---

## Configuration

Copy `.env.example` to `.env`. Common variables:

| Variable | Purpose | Notes |
|----------|---------|--------|
| `MONGODB_URI` | Mongo connection | Default `mongodb://127.0.0.1:27017/vay-reports` |
| `VAY_BOOTSTRAP_PASSWORD` | First admin password | Else `admin123`; change after first login |
| `VAY_COOKIE_SECURE` | Secure session cookie | Set `1` **only** over HTTPS |
| `VAY_CORS_ORIGINS` | CORS allowlist | e.g. Vite origins when not proxied |
| `VAY_EXPORT_DIR` | PDF zip output folder | Default `./vay_reports` |
| `VAY_HOST` / `VAY_PORT` | API bind | Desktop/Docker: `0.0.0.0` / `8765` |
| `VAY_LOGIN_RATE_LIMIT` | Max login attempts | Default `10` |
| `VAY_LOGIN_RATE_WINDOW` | Window (seconds) | Default `300` |
| `VAY_STORE` | Storage backend | `memory` for tests only |
| `VAY_DATA_DIR` | App data directory | Desktop: `%APPDATA%/Vay Reports` or `~/.vay-reports` |
| `VAY_MONGO_PORT` | Bundled mongod port | Default `27018` (Electron) |
| `VAY_CLIENT` | Force thin-client mode | `1` / `true` |
| `VAY_SERVER_URL` | Client backend URL | Else `server.json` / `config.json` |
| `VAY_API_ORIGIN` | Vite proxy target | Default `http://127.0.0.1:8000` |

**Ports at a glance**

| Mode | API / UI | Mongo |
|------|----------|--------|
| Local Vite + uvicorn | UI `5173`, API `8000` | `27017` |
| Docker / packaged desktop | `8765` | `27017` (Docker) or `27018` (bundled) |
| Thin client | Remote host’s `8765` | On the server only |

---

## API surface (summary)

Authenticated product API under `/api/…`, including:

- **Auth / health** — `/api/auth/*`, `/api/health`, `/api/info`
- **Data** — `/api/mappers/*`, `/api/uploads*`, `/api/import-jobs/*`, `/api/rows`
- **Runs** — `/api/runs*` (create, poll, snapshots)
- **Views** — `/api/dashboard`, `/api/invoices*`, `/api/customers*`, `/api/groups*`, `/api/reps*`, `/api/items*`
- **Settings / admin** — `/api/settings/*`, `/api/users`, `/api/roles`, `/api/data/cleanup`, `/api/data/factory-reset`

---

## Tests and fiscal goldens

```text
# CI-style (in-memory store)
set VAY_STORE=memory
pytest
```

Golden tests compare current-FY fiscal slices by entity key with `#,##0.00` tolerance. Regenerate checked-in engine goldens with:

```text
python scripts/make_engine_golden.py
```

See [`tests/fixtures/gs_golden/README.md`](tests/fixtures/gs_golden/README.md) for replacing them with a real Google Sheets export.

---

## Build & deploy notes

| Path | Notes |
|------|--------|
| **Docker** | Builds `web` → copies `web/dist` into the image; uvicorn on `8765` |
| **CI** | `VAY_STORE=memory`, `pytest`, `npm run build` in `web/` (no Electron) |
| **Desktop full** | Windows: `build-desktop.ps1` → NSIS `.exe` (firewall for 8765). macOS: `scripts/build-desktop.sh` or `npm run dist:mac` → DMG and PKG in `desktop/release/` |
| **Desktop client** | Windows: `npm run dist:client` → NSIS `.exe`. macOS: `npm run dist:client:mac` → DMG and PKG (no mongo / no `vay-api`) |

Gitignored / generated artifacts include `.env`, `web/dist`, `desktop/vendor`, `desktop/release`, `vay_reports/`, and `/dist/`.

---

## License & third-party notes

- Packaged desktop downloads **MongoDB Community** under the [SSPL](https://www.mongodb.com/licensing/server-side-public-license).
- Use LAN deployments only on **trusted networks**; enable HTTPS (`VAY_COOKIE_SECURE=1`) when exposing beyond a private LAN.
