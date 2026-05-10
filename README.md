# Bon Bon Oil ERP (Full System)

Bon Bon Oil ERP is a full-stack enterprise system for voucher sales, customer/debt management, inventory, production, expenses, reporting, and finance ledger workflows.

This repository contains:
- `backend/`: FastAPI + PostgreSQL + Redis API service
- `frontend/`: React + TypeScript + Vite web app

## Core Features

- Authentication with access/refresh JWT tokens
- Role-based access (`super_admin`, `admin`, `manager`, `cashier`, `warehouse`)
- Voucher lifecycle (draft, confirm, pay, void) with idempotency support
- Inventory item management and stock movement tracking
- Production batch planning and completion flows
- Customer profiles, balances, and debt/payment tracking
- Expense recording and approval/payment flow
- Finance module with accounts, payment methods, journal entries, customer debts
- Audit logs and reporting endpoints
- Health checks and structured logging

## Tech Stack

### Backend
- Python 3.13
- FastAPI, SQLAlchemy (async), Alembic
- PostgreSQL 16
- Redis 7
- Pytest, Ruff, Mypy
- Docker / Docker Compose

### Frontend
- React 19 + TypeScript
- Vite 8
- React Router
- TanStack Query
- Axios
- Zustand
- i18next (English + Burmese)
- Tailwind CSS + Radix UI

## Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── core/           # config, security, logging, exceptions
│   │   ├── database/       # SQLAlchemy + Redis setup
│   │   ├── middleware/     # request-id, timing, audit, idempotency
│   │   ├── modules/        # auth/users/customers/inventory/...
│   │   └── main.py         # FastAPI app factory + router registration
│   ├── alembic/            # DB migrations
│   ├── scripts/            # seed + superadmin scripts
│   ├── tests/              # integration/unit tests
│   ├── docker-compose.yml
│   └── Makefile
├── frontend/
│   ├── src/
│   │   ├── api/            # API clients per domain
│   │   ├── features/       # page-level feature modules
│   │   ├── components/      # layout + ui components
│   │   ├── router/         # route definitions + guards
│   │   ├── store/          # Zustand stores
│   │   └── i18n/           # translations (en/mm)
│   └── package.json
└── README.md
```

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ and npm
- Python 3.13 (for local backend dev without Docker)

## Environment Setup

### Backend

1. Create backend env file:

```bash
cd backend
cp .env.example .env
```

2. Update at least these values in `.env`:
- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`

### Frontend

1. Create frontend env file:

```bash
cd frontend
cp .env.example .env
```

Note: the frontend currently uses relative `/api/v1` calls and Vite proxy during development.

## Run the Full System (Recommended)

### 1. Start backend services (API + Postgres + Redis)

```bash
cd backend
make dev
```

Backend endpoints:
- API base: `http://localhost:8000/api/v1`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 2. Apply migrations

In another terminal:

```bash
cd backend
make migrate
```

### 3. Seed finance/payment reference data

```bash
cd backend
make seed
```

### 4. Create first super admin user

```bash
cd backend
make superadmin
```

### 5. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend app:
- `http://localhost:5173`

## Backend Local Development (Without Docker API container)

If you want to run API directly on your machine (while keeping DB/Redis in Docker):

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# Set POSTGRES_HOST=localhost and REDIS_HOST=localhost in .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Quality and Test Commands

### Backend

```bash
cd backend
make test
make test-unit
make test-int
make lint
make format
make typecheck
```

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

## API Module Map (`/api/v1`)

- `/auth` - login/refresh/me/logout/change-password
- `/users` - user profile + admin user management
- `/customers` - customer CRUD and summaries
- `/inventory` - inventory items and movements
- `/production` - production batches and consumption/output
- `/expenses` - expense workflows
- `/reporting` and `/reports` - dashboards and report endpoints
- `/finance` - accounts, payment methods, debts, journal entries
- `/vouchers` - voucher transactions and lifecycle
- `/audit` - audit log access

## Domain and Data Integrity Notes

Business rules are documented in:
- `backend/docs/business_rules.md`

Important protections implemented in backend services:
- Transactional workflows with locking for concurrency safety
- Idempotency middleware for duplicate request protection
- Append-only reversal logic for vouchers/ledger/inventory events
- Standardized error response shape and request tracing headers

## Common Operations

### Stop backend containers

```bash
cd backend
make down
```

### View backend logs

```bash
cd backend
make logs
```

### Create a new migration

```bash
cd backend
make migrate-new MSG="describe change"
```

## Troubleshooting

- If frontend cannot reach API, confirm backend is running on `http://localhost:8000` and Vite dev server is running from `frontend/`.
- If backend fails at startup, check `.env` values, especially DB/Redis credentials.
- If migrations fail, ensure Postgres container is healthy and `.env` DB values match compose values.
- If login fails for all users, create a super admin again with `make superadmin`.

## Current Status Notes

- Frontend `frontend/README.md` is the default Vite template and not project-specific.
- This root `README.md` is the primary documentation entrypoint for the full system.
