# FinPay / FinPau

A production-oriented fintech wallet application implementing the foundation of
the [dependency-first SRS](./FinPay_FinPau_Dependency_First_Implementation_SRS_v2.md):
secure authentication, an idempotent transaction engine, persistent
notifications, and real-time Socket.IO delivery backed by a database source of
truth.

## Architecture

```
React / Vite  ──REST──▶  FastAPI  ──▶  Services  ──▶  PostgreSQL (source of truth)
      ▲                     │                              │
      └──── Socket.IO ◀─────┴──── Domain events ◀──────────┘
```

- **Backend:** FastAPI + SQLAlchemy 2 + Alembic + python-socketio, JWT auth
  (PyJWT), Argon2 password hashing, PostgreSQL, Redis (Socket.IO manager).
- **Frontend:** React 18 + Vite + react-router + socket.io-client with a single
  managed socket connection and central auth state.

## What is implemented (Milestones M1–M5 core + real-time)

- Application foundation, config, logging, error envelope.
- Auth: register → OTP verification → login, JWT access/refresh, sessions.
- Wallet + ledger + transaction engine with a persisted state machine
  (`CREATED → PENDING → PROCESSING → SUCCESS`) and idempotency keys.
- Notifications persisted first, then delivered over Socket.IO (`notification:new`),
  with unread counts and deduplication by `event_id`.
- Real-time events: `TRANSACTION_SUCCESS`, `WALLET_BALANCE_UPDATED` scoped to a
  per-user room (`user:{id}`); unauthenticated sockets are rejected.
- Dashboard, services catalog, transaction history APIs.

## Local development

Requirements are provisioned automatically by the Cloud Agent environment
(`.cursor/environment.json`). To run manually:

```bash
# System services
./scripts/start-services.sh          # PostgreSQL + Redis

# One-time / idempotent setup (deps + migrations)
./scripts/setup.sh

# Backend (http://localhost:8000)
cd backend && . .venv/bin/activate && uvicorn app.main:asgi --host 0.0.0.0 --port 8000

# Frontend (http://localhost:5173)
cd frontend && npm run dev
```

The Vite dev server proxies `/api` and `/socket.io` to the backend, so the app
runs from a single origin.

### Backend layout

```
backend/app/
├── core/         config, security (JWT + Argon2), logging, error envelope
├── db/           SQLAlchemy engine, declarative base
├── models/       users, otp, tokens, wallet/ledger, transactions, notifications
├── schemas/      Pydantic v2 request/response models
├── services/     auth, wallet/transaction engine, notifications
├── routers/      auth, users, wallet, transactions, dashboard, services, notifications
├── events/       standard real-time event envelope
└── websocket/    Socket.IO server (JWT auth, user rooms, thread-safe emit)
```

## API quick reference

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register/initiate` | Start registration, issue OTP |
| POST | `/api/v1/auth/register` | Create pending user |
| POST | `/api/v1/auth/verify-otp` | Activate account, provision wallet, return JWTs |
| POST | `/api/v1/auth/login` | Authenticate, return JWTs |
| GET | `/api/v1/me` | Current user |
| GET | `/api/v1/wallet` | Wallet balance |
| POST | `/api/v1/wallet/add-money` | Credit wallet (idempotent, emits realtime events) |
| GET | `/api/v1/transactions` | Transaction history |
| GET | `/api/v1/dashboard/summary` | Dashboard aggregate |
| GET | `/api/v1/notifications` | Notification history |
| GET | `/api/v1/notifications/unread-count` | Unread count |

In development, OTP codes are returned in the API response (`EXPOSE_OTP_IN_RESPONSE=true`)
to simplify testing.
