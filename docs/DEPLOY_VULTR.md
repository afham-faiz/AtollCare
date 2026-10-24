# Deploy to Vultr (runbook)

**Shape:** a Vultr Cloud Compute instance runs Caddy (automatic HTTPS) → the Next.js web app and the FastAPI engine.
Data lives in **Tiger Cloud** (recommended), or in the bundled TimescaleDB container. The **Presage bridge stays on
the crew laptop** next to the camera; it posts numbers to the engine over HTTPS, and video never leaves the vehicle.

```
crew laptop (Chrome + presage-bridge) ──HTTPS──► Vultr: Caddy ─┬─ /api/* → engine ──► Tiger Cloud
hospital browser ───────────────────────HTTPS──►               └─ /*     → web
```

Both images were built and checked locally (`docker compose -f docker-compose.prod.yml build`), and the engine's
full test suite passes against TimescaleDB 2.31 / Postgres 17.

## 1. Create the server (5 min)

Vultr → **Deploy** → Cloud Compute (shared CPU) → **Ubuntu 24.04 LTS** → **2 vCPU / 4 GB** at least (the web build
needs the memory) → the region closest to where you demo (London = `lhr`). Under **SSH Keys** add your public key.
Firewall group: allow inbound **22, 80, 443**.

## 2. Prepare `.env` on your machine (repo root)

Copy `.env.example` to `.env` and set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Tiger Cloud service URL (`postgres://…?sslmode=require`). Leave the example value to use the bundled container instead |
| `PUBLIC_HOST` | `<server-ip>.sslip.io` (instant Let's Encrypt certificate) or your domain. The script fills it in if missing |
| `GEMINI_MODE=real`, `GEMINI_API_KEY` | Gemini |
| `ELEVENLABS_MODE=real`, `ELEVENLABS_API_KEY` | ElevenLabs (Text to Speech + Speech to Text permissions) |
| `HOST_LABEL=Vultr`, `HOST_REGION=lhr` | Only if the presenter panel shows "This computer" after deploy (the engine normally reads Vultr's metadata service itself) |

`.env` is never committed. The deploy script copies it to the server the first time; after that, edit it on the
server (`/opt/atollcare/.env`) and redeploy.

## 3. Deploy

From the repo root, in Git Bash, WSL, macOS or Linux:

```bash
VULTR_HOST=<server-ip> ./scripts/deploy_vultr.sh
```

The default mode ships the **committed** tree with `git archive` over SSH (no rsync or GitHub access needed on the
server), installs Docker if missing, and runs `docker compose -f docker-compose.prod.yml up -d --build`. Options:
`SSH_KEY=~/.ssh/<key>`, `MODE=rsync` (include uncommitted changes), `MODE=git BRANCH=<branch>` (server pulls from
GitHub). The first build takes a few minutes.

## 4. Check it

```bash
curl -s https://<server-ip>.sslip.io/api/health
```

Open `https://<server-ip>.sslip.io` → it lands on the crew screen. Press **Ctrl + .** — under *Services*:

- **Database:** `Tiger Cloud · TimescaleDB 2.x` (or `TimescaleDB` for the container)
- **Host:** `Vultr · LHR` — read from the instance metadata service, not assumed

Then **Network insights → Seed 60 days of history** (about 10–20 s) and open the insights page.

## 5. Point the Presage bridge at the server

On the crew laptop, in the repo's `.env`: `PRESAGE_API_KEY=…` and `ENGINE_URL=https://<server-ip>.sslip.io`. Then:

```bash
cd presage-bridge && node --env-file=../.env src/index.js
```

Open `https://<server-ip>.sslip.io/crew` in **Chrome or Edge** and allow the camera. The page talks to the bridge at
`ws://localhost:8787`; recent Chrome versions ask to allow access to devices on your local network — click **Allow**.

## Updating

Commit, then rerun `VULTR_HOST=<server-ip> ./scripts/deploy_vultr.sh`. Data in Tiger Cloud is untouched.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Web build killed / exits 137 | Out of memory: use 4 GB+, or add swap (`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`) |
| Certificate errors | Ports 80/443 open in the Vultr firewall; `PUBLIC_HOST` matches the IP; check `docker compose -f docker-compose.prod.yml logs caddy` |
| Engine restarts, "database not ready" | Tiger URL wrong or missing `?sslmode=require`; `docker compose -f docker-compose.prod.yml logs engine` |
| Crew screen: "Not measuring · Presage bridge offline" | Bridge not running on the laptop, or Chrome blocked local network access (site settings) |
| Presenter shows "This computer" on Vultr | Set `HOST_LABEL=Vultr` and `HOST_REGION=<code>` in the server's `.env`, redeploy |

## Optional: Vultr Object Storage

ElevenLabs audio is cached on the instance disk by default. To use Object Storage instead: create a bucket, then set
`STORAGE_MODE=s3`, `S3_ENDPOINT=https://<region>.vultrobjects.com`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
This path has not been tested yet.
