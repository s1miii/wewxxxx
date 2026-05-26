# Bankr Bot — Claim Fee Monitor

Real-time monitoring dashboard + Telegram alerter for Bankr Bot fee claims on Base chain.

- **Live Dashboard** → https://twitter-claim-watch.emergent.host
- **Backend** — FastAPI + MongoDB, runs an asyncio indexer polling Base RPC for `Released` events
- **Telegram Alerter** — pushes formatted claim cards to a Telegram channel with X handle, follower count, MC, liquidity, and inline buttons

## Keeping Telegram alerts running 24/7

Emergent's deployed container pauses when there's no traffic, which stops the indexer.
**Fix:** Have UptimeRobot ping `https://twitter-claim-watch.emergent.host/api/health`
every 5 minutes (free, takes 2 min to set up). See section below.

### UptimeRobot setup (2 min, free)

1. Sign up at https://uptimerobot.com
2. **+ Add New Monitor**
3. Type: `HTTP(s)`
4. URL: `https://twitter-claim-watch.emergent.host/api/health`
5. Interval: `5 minutes`
6. **Create Monitor**

Done. Container stays awake 24/7. Telegram alerts never miss a claim.

## Environment variables (`backend/.env`)

| Var | Purpose |
|---|---|
| `MONGO_URL` | MongoDB connection string |
| `DB_NAME` | DB name |
| `BANKR_API_KEY` | Bankr authenticated API (token-launches lookups) |
| `TELEGRAM_BOT_TOKEN` | Bot token for the alert channel |
| `TELEGRAM_CHAT_ID` | Channel ID (negative integer for channels) |
| `TELEGRAM_ENABLED` | `true` / `false` to globally toggle alerts |
| `TWITTERAPI_IO_KEY` | twitterapi.io key for follower count + blue tick |

## Key endpoints

- `GET /api/`           → service banner + indexer last block
- `GET /api/health`     → lightweight uptime ping (use for UptimeRobot)
- `GET /api/claims/feed?limit=30`
- `GET /api/leaderboard/lifetime?limit=12`
- `POST /api/telegram/test` → send a sample card to verify Telegram wiring
