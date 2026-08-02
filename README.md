# Bon Bon Oil ERP

A production-oriented ERP/POS system for a Myanmar cooking-oil manufacturing and distribution business. It runs the full sales-to-cash cycle — sales vouchers, inventory ledger, production batches, customer credit/debt, and double-entry accounting — for internal staff (cashiers, warehouse, managers, admins) rather than end customers.

## Tech Stack

### Backend (`backend/`)
- **Language/framework:** Python 3.13, FastAPI (`fastapi[standard]` ≥0.115), Pydantic v2, `pydantic-settings`
- **Persistence:** PostgreSQL 16, SQLAlchemy 2.0 (async, via `asyncpg`), Alembic migrations
- **Cache/sessions:** Redis 7 (`redis[hiredis]`) — used for idempotency-key caching and auth token blacklisting
- **Auth/security:** `python-jose` (JWT), `bcrypt` password hashing
- **Observability:** `structlog` (structured JSON logs), custom request-ID/timing/audit middleware
- **Serialization:** `orjson`
- **Quality tooling:** Pytest + pytest-asyncio, Ruff (lint+format), Mypy (strict), pre-commit
- **Ops:** Dockerfile (multi-stage: development/production), `postgres-backup-local` + `rclone` sidecar containers for hourly local + Cloudflare R2 offsite Postgres backups

### Frontend (`frontend/`)
- **Core:** React 19.2, TypeScript ~6.0, Vite 8
- **Data/state:** TanStack Query v5 (+ `@tanstack/react-query-persist-client`), Zustand, Axios
- **UI:** Tailwind CSS 4, Radix UI primitives, `lucide-react` icons, `cmdk`, `recharts`
- **Forms/validation:** React Hook Form + Zod
- **Offline/PWA:** `vite-plugin-pwa`, `idb`, `localforage` — local IndexedDB persistence and a pending-uploads queue
- **i18n:** i18next / react-i18next, English + Burmese (`src/i18n/en.json`, `mm.json`)
- **Routing:** React Router v7
- **Deployment target:** Vercel (SPA rewrite in `vercel.json`)

## Key Features (verified in code)

- **Sales vouchers** (`app/modules/vouchers`) — draft → confirm → void lifecycle; line items, split payments, optimistic-locking (`version_number`) for concurrent edits, offline sync fields (`sync_status`, `client_generated_id`).
- **Ledger-based inventory** (`app/modules/inventory`) — append-only `InventoryMovement` ledger is the source of truth; `InventoryItem.current_balance` is a denormalized fast-read cache recomputable from the ledger; point-in-time `InventorySnapshot`s for reporting.
- **Production batches** (`app/modules/production`) — batch runs consume raw materials (triggering `PRODUCTION_CONSUMPTION` inventory movements) and produce finished-oil output (`PRODUCTION_OUTPUT` movements); tracks material/labour/overhead cost and expected-vs-actual yield loss.
- **Double-entry finance** (`app/modules/finance`) — chart of accounts (`FinancialAccount`), an immutable append-only `JournalEntry` ledger (corrections happen via reversal entries, never mutation/deletion), `CustomerDebt` lifecycle (outstanding → partially paid → paid / written off), instalment `DebtPayment`s, and daily/monthly `FinancialSnapshot`s for fast balance queries.
- **Customers** (`app/modules/customers`) — profiles, credit limits.
- **Expenses** (`app/modules/expenses`) — expense recording, tied into the ledger.
- **Audit logging** (`app/modules/audit` + `AuditLogMiddleware`) — captures state-changing requests.
- **Idempotency** (`app/modules/idempotency` + `IdempotencyMiddleware`) — `Idempotency-Key` header protection on voucher confirm/void, expense creation, debt payments, and production batch completion; replays a cached response for a repeated key, returns 409 if the same key is reused with a different body.
- **RBAC** (`app/modules/users/enums.py`) — five roles (`super_admin`, `admin`, `manager`, `cashier`, `warehouse`) with a numeric role-hierarchy check (`has_permission`).
- **JWT auth** (`app/modules/auth`) — access + refresh tokens, bcrypt password hashing with rehash detection, account lockout after 5 failed logins (30 min), Redis-backed logout/blacklist.
- **Reporting** (`app/modules/reporting`) — read-side aggregation endpoints over the above modules.
- **Frontend offline support** — `useOnlineStatus`/`usePendingUploads` hooks, local IndexedDB (`src/db`), PWA service worker.
- **Multi-tenant scaffolding, not active multi-tenancy** — every core table carries a `tenant_id` column (`TenantMixin`) defaulted to `"default"`; per the code's own docstring this is deliberately unused single-tenant infrastructure laid down to avoid a future migration, not a live feature.

### Referenced but not actually implemented
- **Celery**: `.env.example` has `CELERY_*` variables and several docstrings mention "the Celery snapshot task" / "Celery cleanup task", but there is no Celery dependency in `pyproject.toml` and no Celery app/worker code anywhere in the repo — these are aspirational comments only. Snapshot/cleanup jobs are not currently automated by the app itself.
- **CI pipelines**: no `.github/workflows` exist in this repo.
- **LICENSE**: no `LICENSE` file is present in the repo.

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── core/          # settings, security (JWT/bcrypt), exceptions, logging
│   │   ├── database/      # async engine/session, Redis client, ORM mixins (audit, soft-delete, tenant, optimistic lock, sync)
│   │   ├── middleware/    # request-id, timing, audit-log, idempotency
│   │   ├── common/        # shared repositories/schemas/services/utils
│   │   └── modules/       # one package per domain: auth, users, customers, inventory,
│   │                      #   production, finance, vouchers, expenses, audit, idempotency, reporting
│   │       └── <module>/  # models.py, schemas.py, repositories.py, services.py, routes.py, enums.py
│   ├── alembic/versions/  # hand-numbered migrations (001_initial_schema … 006_voucher_item_price_per_viss)
│   ├── scripts/           # seed_data.py, create_superadmin.py, rclone-sync.sh
│   ├── tests/              # unit/ and integration/ (pytest, factory-boy, faker)
│   ├── backups/           # daily/weekly/monthly/last local Postgres dumps (from db-backup container)
│   └── docker-compose.yml # postgres, redis, api, db-backup, backup-uploader (R2)
└── frontend/
    ├── src/
    │   ├── api/            # one client module per backend module (axios)
    │   ├── features/       # one folder per domain (auth, customers, inventory, production, vouchers, expenses, users, reports, dashboard)
    │   ├── store/           # zustand stores (auth, ui)
    │   ├── db/              # IndexedDB (offline persistence)
    │   ├── i18n/            # en.json / mm.json
    │   └── router/          # react-router routes + ProtectedRoute
    └── vercel.json          # SPA rewrite for Vercel hosting
```

## Getting Started / Local Dev Setup

### Prerequisites
- Docker & Docker Compose (recommended path)
- Node.js (for the frontend)
- Python 3.13 (only needed for running the backend outside Docker)

### 1. Configure environment
```bash
cd backend && cp .env.example .env      # fill in real secrets, DB/Redis passwords, JWT secret, etc.
cd ../frontend && cp .env.example .env   # set VITE_API_BASE_URL
```
Never commit real `.env` values.

### 2. Start backend infrastructure (Postgres, Redis, API, backup sidecars)
```bash
cd backend
make dev          # docker compose up --build (foreground)
# or
make up           # detached
```

### 3. Apply migrations and seed data
```bash
cd backend
make migrate       # alembic upgrade head
make seed          # scripts/seed_data.py — reference data (payment methods, etc.)
make superadmin    # scripts/create_superadmin.py — creates first super_admin user
```

### 4. Run the frontend
```bash
cd frontend
npm install
npm run dev         # http://localhost:5173
```

### Quality checks
```bash
# Backend
cd backend
make test          # pytest
make test-unit      # pytest -m unit
make test-int        # pytest -m integration
make lint            # ruff check
make format          # ruff format
make typecheck        # mypy (strict)

# Frontend
cd frontend
npm run lint
npm run build         # tsc -b && vite build
```

All `make` targets above are read directly from `backend/Makefile`.

## Architecture Notes

- **Ledger-first design, twice over.** Both inventory and finance follow the same pattern: an append-only, immutable transaction log (`InventoryMovement`, `JournalEntry`) is the single source of truth, with a denormalized "current balance" column kept in sync transactionally purely as a read-optimization. Corrections are never done by mutating history — inventory uses `correction` movement types, finance uses reversal `JournalEntry` rows linked via `reversal_of_id`.
- **Double-entry accounting is real double-entry.** `FinancialAccount.normal_balance` is derived once at account-creation time from `AccountType` (assets/expenses are debit-normal; liabilities/equity/revenue are credit-normal) via `get_normal_balance()`, so balance math never has to re-derive the accounting identity ad hoc.
- **Snapshots are a caching layer, not a source of truth.** `FinancialSnapshot` and `InventorySnapshot` exist purely so reporting doesn't have to replay the full ledger; both are documented as recomputable from the underlying ledger at any time.
- **Idempotency is scoped, not global.** Only five specific mutating routes are protected by `IdempotencyMiddleware` (voucher confirm/void, expense create, debt payment, production batch complete) — matched by regex against the request path, not applied blanket-wide.
- **Concurrency control is optimistic, not pessimistic.** `OptimisticLockMixin` (a `version_number` counter, bumped on every state-changing action) and `SyncMixin` (`sync_version`, `client_generated_id`, `device_id`, `sync_status`) are composed onto `Voucher`, `InventoryItem`, and `ProductionBatch` — the entities expected to be edited from multiple devices/offline clients.
- **UUIDs are generated in the application layer** (`uuid4()` in Python, with a `gen_random_uuid()` DB-level fallback for raw-SQL inserts), so parent/child rows can be batch-inserted without a round-trip to fetch generated IDs.
- **Multi-tenancy is scaffolding, not a live feature.** Every `FullAuditMixin`-based table carries `tenant_id` defaulted to `"default"`; the code comments are explicit that this is single-tenant today and the column exists only to avoid a future migration.
- **Migrations are hand-written and numbered** (`001_initial_schema.py` … `006_voucher_item_price_per_viss.py`), not purely autogenerated — see `alembic/versions/`.

---
*Business-rule detail beyond what's summarized here lives in `backend/docs/business_rules.md`.*
