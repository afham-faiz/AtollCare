# Deploy to Vultr (runbook)

**Shape:** a Vultr Cloud Compute instance runs Caddy (automatic HTTPS) → the Next.js web app and the FastAPI engine.
Data lives in **Tiger Cloud** (recommended), or in the bundled TimescaleDB container. The **Presage bridge stays on
the crew laptop** next to the camera; it posts numbers to the engine over HTTPS, and video never leaves the vehicle.

```
crew laptop (Chrome + presage-bridge) ──HTTPS──► Vultr: Caddy ─┬─ /api/* → engine ──► Tiger Cloud (or TimescaleDB container)
hospital browser ───────────────────────HTTPS──►               └─ /*     → web
```

**Verified so far:** engine tests (89, in-memory store), `bun run typecheck`, `bun run lint` and the production
`next build` (standalone output) pass. **Not yet verified:** the Docker images and the migrations against a real
TimescaleDB / Tiger Cloud — the first deploy is that test. Timescale-only statements (aggregates, policies,
compression) are skipped with a log warning if they fail, so they can't stop the engine booting.

## 1. Create the server (5 min)

Vultr → **Deploy** → Cloud Compute (shared CPU) → **Ubuntu 24.04 LTS** → **2 vCPU / 4 GB** recommended (the web
build needs the memory; on 2 GB the script adds 2 GB swap) → the region closest to where you demo (London = `lhr`).
Under **SSH Keys** add your public key. Firewall group: allow inbound **22, 80, 443**.

## 2. Prepare `.env` on your machine (repo root)

Copy `.env.example` to `.env` and set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Tiger Cloud service URL (`postgres://…?sslmode=require`). Leave the example value (or empty) to use the bundled container — the script then starts it with `--profile localdb` |
| `PUBLIC_HOST` | `<server-ip>.sslip.io` (instant Let's Encrypt certificate) or your domain. The script fills it in if missing or `localhost` |
| `GEMINI_MODE=real`, `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini. `gemini-flash-lite-latest` answered fastest on event day; `gemini-2.5-flash` is closed to new keys |
| `GEMINI_TIMEOUT_S=25` | Gemini latency was 9–15 s under load |
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
server). First run: installs Docker, adds swap on small instances, opens 80/443 if `ufw` is active. Then it runs
`docker compose -f docker-compose.prod.yml [--profile localdb] up -d --build` and waits for
`https://<PUBLIC_HOST>/api/health`. Options: `SSH_KEY=~/.ssh/<key>`, `MODE=rsync` (include uncommitted changes),
`MODE=git BRANCH=<branch>` (server pulls from GitHub), `REF=<commit>` (archive another commit). The first build takes
a few minutes.

## 4. Check it

```bash
curl -s https://<server-ip>.sslip.io/api/health
```

The response includes `infra`: `{"database": "Tiger Cloud · TimescaleDB 2.x", "host": "Vultr · LHR", …}`.

Open `https://<server-ip>.sslip.io` → it lands on the crew screen. Press **Ctrl + .** — under *Services*:

- **Database:** `Tiger Cloud · TimescaleDB 2.x` (or `TimescaleDB 2.x` for the container)
- **Host:** `Vultr · LHR` — read from the instance metadata service (`169.254.169.254/v1.json`), not assumed

Then **Network insights → Seed 60 days of history** and open **Insights** in the top bar. The source pill should read
`Tiger Data · continuous aggregate` (the `transfer_daily` aggregate over the `transfer_log` hypertable). Every live
transfer that arrives is logged there too.

## 5. Point the Presage bridge at the server

On the crew laptop, in the repo's `.env`: `PRESAGE_API_KEY=…` and `ENGINE_URL=https://<server-ip>.sslip.io`. Then:

```bash
cd presage-bridge && npm install && node --env-file=../.env src/index.js
```

Open `https://<server-ip>.sslip.io/crew` in **Chrome or Edge** and allow the camera. The page talks to the bridge at
`ws://localhost:8787`; recent Chrome versions ask to allow access to devices on your local network — click **Allow**.

## Updating

Commit, then rerun `VULTR_HOST=<server-ip> ./scripts/deploy_vultr.sh`. Data in Tiger Cloud (or the `dbdata` volume)
is untouched.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Web build killed / exits 137 | Out of memory: use 4 GB+ (the script adds 2 GB swap below ~3.8 GB RAM) |
| Certificate errors | Ports 80/443 open in the Vultr firewall; `PUBLIC_HOST` matches the IP; `docker compose -f docker-compose.prod.yml logs caddy` |
| Engine restarts, "database not ready" | Tiger URL wrong or missing `?sslmode=require`; `docker compose -f docker-compose.prod.yml logs engine` |
| Insights pill says "Postgres · raw query" | The continuous aggregate wasn't created (check the engine log for "skipped Timescale statement"); numbers are still correct, just computed from the raw table |
| Crew screen: "Not measuring · Presage bridge offline" | Bridge not running on the laptop, or Chrome blocked local network access (site settings) |
| Presenter shows "This computer" on Vultr | Set `HOST_LABEL=Vultr` and `HOST_REGION=<code>` in the server's `.env`, redeploy |

## Optional: Vultr Object Storage

ElevenLabs audio is cached on the instance disk by default. To use Object Storage instead: create a bucket, then set
`STORAGE_MODE=s3`, `S3_ENDPOINT=https://<region>.vultrobjects.com`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
This path has not been tested yet.
