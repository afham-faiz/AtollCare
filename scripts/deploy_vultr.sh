#!/usr/bin/env bash
# Deploy to a Vultr Cloud Compute instance (Ubuntu) over SSH. Runbook: docs/DEPLOY_VULTR.md
#   VULTR_HOST=1.2.3.4 ./scripts/deploy_vultr.sh                 # ship the committed tree (git archive; works on Windows)
#   VULTR_HOST=1.2.3.4 MODE=rsync ./scripts/deploy_vultr.sh      # ship the working tree, uncommitted changes included
#   VULTR_HOST=1.2.3.4 MODE=git BRANCH=main ./scripts/deploy_vultr.sh  # the server clones/pulls from GitHub
# First run installs Docker if missing. The server needs ports 80/443 open and a .env (copied from yours if absent).
set -euo pipefail

HOST="${VULTR_HOST:?set VULTR_HOST to the instance IP}"
USER_NAME="${VULTR_USER:-root}"
DIR="${REMOTE_DIR:-/opt/atollcare}"
MODE="${MODE:-archive}"
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
REPO="${REPO_URL:-$(git config --get remote.origin.url || true)}"
SSH_KEY="${SSH_KEY:-}"
TARGET="$USER_NAME@$HOST"
SSH=(ssh -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i "$SSH_KEY"})
SCP=(scp -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i "$SSH_KEY"})

echo "→ deploying $BRANCH to $TARGET:$DIR ($MODE)"

"${SSH[@]}" "$TARGET" "command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)"
"${SSH[@]}" "$TARGET" "mkdir -p $DIR"

case "$MODE" in
  git)
    "${SSH[@]}" "$TARGET" "if [ -d $DIR/.git ]; then cd $DIR && git fetch origin $BRANCH && git checkout $BRANCH && git pull --ff-only; \
      else git clone --branch $BRANCH $REPO $DIR; fi"
    ;;
  rsync)
    rsync -az --delete -e "${SSH[*]}" \
      --exclude '.git' --exclude 'node_modules' --exclude '.next' --exclude '.venv' \
      --exclude 'var' --exclude '.env' --exclude '__pycache__' \
      ./ "$TARGET:$DIR/"
    ;;
  archive)
    # committed files of HEAD only — never .env, node_modules or build output
    git archive --format=tar HEAD | "${SSH[@]}" "$TARGET" "tar -x -C $DIR"
    ;;
  *) echo "unknown MODE=$MODE (archive | rsync | git)" >&2; exit 1 ;;
esac

if ! "${SSH[@]}" "$TARGET" "test -f $DIR/.env"; then
  if [ -f .env ]; then
    "${SCP[@]}" .env "$TARGET:$DIR/.env"
  else
    "${SCP[@]}" .env.example "$TARGET:$DIR/.env"
  fi
  "${SSH[@]}" "$TARGET" "grep -q '^PUBLIC_HOST=.*sslip.io' $DIR/.env || sed -i 's/^PUBLIC_HOST=.*/PUBLIC_HOST=$HOST.sslip.io/' $DIR/.env"
fi

"${SSH[@]}" "$TARGET" "cd $DIR && docker compose -f docker-compose.prod.yml up -d --build && docker compose -f docker-compose.prod.yml ps"
PUBLIC_HOST=$("${SSH[@]}" "$TARGET" "grep '^PUBLIC_HOST=' $DIR/.env | cut -d= -f2 | cut -d' ' -f1")
echo "✓ deployed — https://$PUBLIC_HOST"
echo "  check: curl -s https://$PUBLIC_HOST/api/health"
