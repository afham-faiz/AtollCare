# Feedback log (post-one-shot)

Triage together in the first 30 min: run every scenario in `/demo` on desktop and on a 375 px phone, log each problem
below with its feature ID and lane (see README → lanes). One entry per problem; update **Status** as you go.

Template:

```markdown
## FB-001 — <short title>
- **Type:** bug | design | enhancement | cut
- **Feature:** F-M3.3
- **Lane / owner:** C / <name>
- **Severity for demo:** blocker | high | nice-to-have
- **Observed:** what happened (scenario, page, viewport)
- **Expected:** what should happen
- **Notes / fix idea:**
- **Status:** open | in progress | done (commit/PR link)
```

---

## FB-001 — Verify the Docker + TimescaleDB path
- **Type:** bug
- **Feature:** F-M7.1, F-M7.2
- **Lane / owner:** shared / —
- **Severity for demo:** blocker
- **Observed:** not run during the one-shot (Docker unavailable on the build machine)
- **Expected:** `docker compose up` works with no keys; API tests pass with `TEST_DATABASE_URL` pointing at the db
- **Notes / fix idea:** see `KNOWN_ISSUES.md`
- **Status:** open

## FB-002 — Confirm Presage integration path
- **Type:** enhancement
- **Feature:** F-M6.2
- **Lane / owner:** A / —
- **Severity for demo:** high
- **Observed:** `sdk` and `cloud` modes are placeholders (`TODO(presage-verify)`)
- **Expected:** real HR/RR from the 30 s browser recording
- **Notes / fix idea:** ask the Presage booth: Linux SDK binary/binding vs cloud endpoint, accepted video format
- **Status:** in progress. v2 replaced the placeholders with `presage-bridge/` (official `@smartspectra/node-sdk`,
  live frames over a local WebSocket). It needs a real `PRESAGE_API_KEY` and a camera in Chrome or Edge to verify
  (see `KNOWN_ISSUES.md`).
