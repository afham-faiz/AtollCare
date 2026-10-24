#!/usr/bin/env bash
# F-M7.3 Deploy to a Vultr Cloud Compute instance (Ubuntu) over SSH.
#   VULTR_HOST=1.2.3.4 ./scripts/deploy_vultr.sh            # rsync the working tree
#   VULTR_HOST=1.2.3.4 MODE=git ./scripts/deploy_vultr.sh    # git pull on the server instead
# First run installs Docker if missing. The server needs ports 80/443 open and a .env (copied if absent).
set -euo pipefail

HOST="${VULTR_HOST:?set VULTR_HOST to the instance IP}"
USER_NAME="${VULTR_USER:-root}"
DIR="${REMOTE_DIR:-/opt/atollcare}"
MODE="${MODE:-rsync}"
REPO="${REPO_URL:-$(git config --get remote.origin.url || true)}"
TARGET="$USER_NAME@$HOST"

echo "→ deploying to $TARGET:$DIR ($MODE)"

ssh "$TARGET" "command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)"
ssh "$TARGET" "mkdir -p $DIR"

if [ "$MODE" = "git" ]; then
  ssh "$TARGET" "if [ -d $DIR/.git ]; then cd $DIR && git pull --ff-only; else git clone $REPO $DIR; fi"
else
  rsync -az --delete \
    --exclude '.git' --exclude 'node_modules' --exclude '.next' --exclude '.venv' \
    --exclude 'var' --exclude '.env' --exclude '__pycache__' \
    ./ "$TARGET:$DIR/"
fi

if ! ssh "$TARGET" "test -f $DIR/.env"; then
  if [ -f .env ]; then
    scp .env "$TARGET:$DIR/.env"
  else
    scp .env.example "$TARGET:$DIR/.env"
    ssh "$TARGET" "sed -i 's/^PUBLIC_HOST=.*/PUBLIC_HOST=$HOST.sslip.io/' $DIR/.env"
  fi
fi

ssh "$TARGET" "cd $DIR && docker compose -f docker-compose.prod.yml up -d --build && docker compose -f docker-compose.prod.yml ps"
PUBLIC_HOST=$(ssh "$TARGET" "grep '^PUBLIC_HOST=' $DIR/.env | cut -d= -f2 | cut -d' ' -f1")
echo "✓ deployed — https://$PUBLIC_HOST"
