#!/usr/bin/env bash
#
# FinPay Cloud Agent start script.
#
# Per-boot reconciliation: bring up PostgreSQL and Redis. Idempotent and safe to
# run when the services are already running. Returns once services are ready.
set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# --- Redis -----------------------------------------------------------------
if redis-cli ping >/dev/null 2>&1; then
  log "Redis already running"
else
  log "Starting Redis"
  sudo redis-server --daemonize yes --save "" --appendonly no
fi

# --- PostgreSQL ------------------------------------------------------------
# Detect the installed cluster version (do not hard-code 16).
PG_VER="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $1}')"
PG_CLUSTER="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $2}')"
PG_VER="${PG_VER:-16}"
PG_CLUSTER="${PG_CLUSTER:-main}"

if pg_isready -q 2>/dev/null; then
  log "PostgreSQL already accepting connections"
else
  log "Starting PostgreSQL cluster ${PG_VER}/${PG_CLUSTER}"
  sudo pg_ctlcluster "${PG_VER}" "${PG_CLUSTER}" start || true
fi

# Wait for readiness (up to ~30s).
for _ in $(seq 1 30); do
  if pg_isready -q 2>/dev/null; then
    break
  fi
  sleep 1
done

if ! pg_isready -q 2>/dev/null; then
  echo "PostgreSQL did not become ready in time" >&2
  exit 1
fi

log "Services are ready (PostgreSQL + Redis)."
