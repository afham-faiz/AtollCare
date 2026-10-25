#!/usr/bin/env bash
# One HTTPS address for phones. A phone only allows its camera on HTTPS, and Presage's live stream needs wss:// on the
# same footing, so this puts the web app on a Cloudflare quick tunnel. The web app already proxies /api to the engine
# and /presage to the bridge, so this single address carries everything.
#
#   1. start the engine, the Presage bridge and the web app as usual (README "Run locally")
#   2. ./scripts/phone_tunnel.sh          (prints https://<random>.trycloudflare.com)
#   3. open that address on the laptop, press Ctrl + . and scan the "On a phone" QR code with the phone
#
# The address is public while this runs (random and unlisted, but anyone who has it can open the app); stop it with
# Ctrl + C when you're done. For the stage, use a production build (bun run build && bun run start): it loads faster
# on a phone than the dev server.
set -euo pipefail
PORT="${PORT:-3000}"
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared isn't installed: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  echo "(Windows: winget install --id Cloudflare.cloudflared)"
  exit 1
fi
curl -fsS "http://localhost:$PORT/api/health" >/dev/null || { echo "Nothing on http://localhost:$PORT/api/health: start the web app and engine first"; exit 1; }
curl -fsS "http://localhost:$PORT/presage/health" >/dev/null || echo "warning: the Presage bridge isn't answering on /presage/health; scans will fall back to measuring the upload"
# HTTP/2 over TCP: the default QUIC (UDP) crawled on venue-style Wi-Fi in testing (pages took 15 s, phones gave up)
exec cloudflared tunnel --no-autoupdate --protocol "${TUNNEL_PROTOCOL:-http2}" --url "http://localhost:$PORT"
