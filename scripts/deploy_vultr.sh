#!/usr/bin/env bash
# F-M7.3 Deploy to a Vultr Cloud Compute instance (Ubuntu 24.04) over SSH. Runbook: docs/DEPLOY_VULTR.md
#
#   VULTR_HOST=1.2.3.4 ./scripts/deploy_vultr.sh                       # ship the committed tree (git archive), default
#   VULTR_HOST=1.2.3.4 MODE=rsync ./scripts/deploy_vultr.sh            # include uncommitted changes
#   VULTR_HOST=1.2.3.4 MODE=git BRANCH=main ./scripts/deploy_vultr.sh  # the server pulls from GitHub
#
# Options: SSH_KEY=~/.ssh/key  VULTR_USER=root  REMOTE_DIR=/opt/atollcare  REF=HEAD (archive mode)
# First run: installs Docker, adds swap on small instances, opens 80/443 if ufw is active, copies .env (never
# committed) and fills PUBLIC_HOST=<ip>.sslip.io when it is unset or localhost. Later runs keep the server's .env.
set -euo pipefail

HOST="${VULTR_HOST:?set VULTR_HOST to the instance IP}"
USER_NAME="${VULTR_USER:-root}"
DIR="${REMOTE_DIR:-/opt/atollcare}"
MODE="${MODE:-archive}"
REF="${REF:-HEAD}"
BRANCH="${BRANCH:-main}"
REPO="${REPO_URL:-$(git config --get remote.origin.url || true)}"
TARGET="$USER_NAME@$HOST"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
if [ -n "${SSH_KEY:-}" ]; then SSH_OPTS+=(-i "$SSH_KEY"); fi

cd "$(dirname "$0")/.."
remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }
upload() { scp "${SSH_OPTS[@]}" "$1" "$TARGET:$2"; }

echo "→ deploying to $TARGET:$DIR (mode: $MODE)"

# ---------------------------------------------------------------- server prerequisites (idempotent)
remote bash -s <<'PREREQ'
set -e
command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)
# the Next.js build needs ~3 GB; add swap on smaller instances
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
if [ "$mem_kb" -lt 3800000 ] && ! swapon --show | grep -q /swapfile; then
  echo "  adding 2 GB swap (RAM: $((mem_kb / 1024)) MB)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
fi
PREREQ
remote "mkdir -p $DIR"

# ---------------------------------------------------------------- code
case "$MODE" in
  archive)
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
      echo "  note: uncommitted changes are NOT shipped in archive mode (use MODE=rsync to include them)"
    fi
    echo "  shipping $(git rev-parse --short "$REF") via git archive"
    git archive --format=tar "$REF" | remote "tar -x -C $DIR"
    ;;
  rsync)
    rsync -az --delete -e "ssh ${SSH_OPTS[*]}" \
      --exclude '.git' --exclude 'node_modules' --exclude '.next' --exclude '.venv' \
      --exclude 'var' --exclude '.env' --exclude '__pycache__' \
      ./ "$TARGET:$DIR/"
    ;;
  git)
    remote "command -v git >/dev/null || (apt-get update -qq && apt-get install -y -qq git)"
    remote "if [ -d $DIR/.git ]; then cd $DIR && git fetch -q origin && git checkout -q $BRANCH && git pull -q --ff-only origin $BRANCH; else git clone -q --branch $BRANCH $REPO $DIR; fi"
    ;;
  *)
    echo "unknown MODE=$MODE (archive | rsync | git)" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------- .env (first run only)
if ! remote "test -f $DIR/.env"; then
  if [ -f .env ]; then
    echo "  copying local .env to the server"
    upload .env "$DIR/.env"
  else
    echo "  no local .env — starting from .env.example (mock adapters)"
    upload .env.example "$DIR/.env"
  fi
fi
# PUBLIC_HOST must be the public name for Caddy's certificate; fill it if unset or still localhost
remote "cd $DIR && if ! grep -qE '^PUBLIC_HOST=[^[:space:]]+' .env || grep -qE '^PUBLIC_HOST=(localhost|127\.0\.0\.1)[[:space:]]*$' .env; then
  sed -i '/^PUBLIC_HOST=/d' .env && echo 'PUBLIC_HOST=$HOST.sslip.io' >> .env && echo '  PUBLIC_HOST set to $HOST.sslip.io'; fi"
# the bundled TimescaleDB container runs only when DATABASE_URL is empty or points at it (otherwise e.g. Tiger Cloud)
PROFILE_ARGS=""
if remote "cd $DIR && { ! grep -qE '^DATABASE_URL=[^[:space:]]+' .env || grep -qE '^DATABASE_URL=postgres(ql)?://[^@]*@db:' .env; }"; then
  PROFILE_ARGS="--profile localdb"
  echo "  database: bundled TimescaleDB container"
else
  echo "  database: external (DATABASE_URL in the server's .env)"
fi

# ---------------------------------------------------------------- build + run
remote "cd $DIR && docker compose -f docker-compose.prod.yml $PROFILE_ARGS up -d --build --remove-orphans && docker compose -f docker-compose.prod.yml $PROFILE_ARGS ps"
PUBLIC_HOST=$(remote "grep '^PUBLIC_HOST=' $DIR/.env | tail -1 | cut -d= -f2 | tr -d '[:space:]'")

# ---------------------------------------------------------------- health check (Caddy may need a moment for the certificate)
echo "→ waiting for https://$PUBLIC_HOST/api/health"
for _ in $(seq 1 40); do
  if body=$(curl -fsS --max-time 5 "https://$PUBLIC_HOST/api/health" 2>/dev/null); then
    echo "  $body"
    echo "✓ deployed — https://$PUBLIC_HOST"
    exit 0
  fi
  sleep 3
done
echo "! no healthy response yet. Check: ssh $TARGET 'cd $DIR && docker compose -f docker-compose.prod.yml logs --tail 50 caddy engine'" >&2
exit 1
