#!/usr/bin/env bash
#
# FinPay Cloud Agent install script.
#
# Durable, idempotent repository bootstrap: system packages, service readiness,
# Python/Node dependencies, and database migrations. Safe to run repeatedly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PG_USER="${FINPAY_DB_USER:-finpay}"
PG_PASSWORD="${FINPAY_DB_PASSWORD:-finpay}"
PG_DB="${FINPAY_DB_NAME:-finpay}"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# --- 1. System packages (idempotent) --------------------------------------
if ! command -v psql >/dev/null 2>&1 || ! command -v redis-server >/dev/null 2>&1 \
    || ! dpkg -s python3-venv >/dev/null 2>&1; then
  log "Installing system packages (postgresql, redis, python venv, build tools)"
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postgresql postgresql-contrib redis-server \
    python3-venv python3-dev build-essential libpq-dev
else
  log "System packages already present"
fi

# --- 2. Start services so migrations can run -------------------------------
log "Ensuring PostgreSQL and Redis are running"
"$ROOT_DIR/scripts/start-services.sh"

# --- 3. Ensure database role and database (idempotent) ---------------------
log "Ensuring database role and database exist"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${PG_USER}') THEN
      CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASSWORD}';
   END IF;
END
\$\$;
SQL
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
  sudo -u postgres createdb -O "${PG_USER}" "${PG_DB}"
fi

# --- 4. Backend dependencies ------------------------------------------------
log "Setting up backend virtualenv and dependencies"
cd "$ROOT_DIR/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip -q
pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
fi

# --- 5. Database migrations -------------------------------------------------
log "Applying database migrations"
alembic upgrade head
deactivate

# --- 6. Frontend dependencies ----------------------------------------------
log "Installing frontend dependencies"
cd "$ROOT_DIR/frontend"
npm install --no-audit --no-fund
if [ ! -f .env ]; then
  cp .env.example .env
fi

log "FinPay setup complete."
