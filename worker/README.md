# Bankr Telegram Alerter — Railway Worker

Stateless 24/7 Telegram alerter for Bankr Bot fee claims on Base chain.
Designed to run on **Railway** (or any always-on worker host) so your Telegram
alerts keep flowing even when the Emergent dashboard container is asleep.

The Emergent dashboard (https://twitter-claim-watch.emergent.host) keeps
running independently. This worker has **no shared database** — it's a pure
relay: watch chain → format alert → send to Telegram.

---

## What it does

1. Polls Base chain every `POLL_INTERVAL_S` seconds (default 15s) for
   `Released` events emitted by the Bankr / Doppler `StreamableFeesLocker`
   contracts.
2. Pulls token metadata (name, symbol, decimals) on-chain.
3. Resolves the beneficiary's X handle via the Bankr API (`/token-launches/{addr}`).
4. Fetches follower count + blue-tick status from twitterapi.io.
5. Fetches market cap & liquidity from DexScreener.
6. Sends a fully-formatted message with inline buttons to your Telegram channel.

It dedupes events in memory (last 2000 events), so a restart won't double-send
alerts beyond the configurable `INITIAL_LOOKBACK_BLOCKS` window (default: 5
blocks, ~10 seconds of chain history).

---

## Deploy to Railway (the fast way)

### 1. Create a Railway account
- Sign up at https://railway.app (free tier includes $5/month credit — plenty
  for one always-on Python container).
- Verify your email.

### 2. New project from GitHub
- In Emergent chat, hit **"Save to GitHub"** to push this whole repo.
- On Railway: **New Project → Deploy from GitHub repo → pick your repo**.
- When asked for the root directory, set it to: `worker`
  (Railway will then use `worker/Dockerfile` automatically).

### 3. Set environment variables
In your Railway service → **Variables** tab, add:

| Variable | Value | Required |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `8335281387:AAH5KfMmXgtkhERBtCEeQsCbraA6zEvr30w` | ✅ yes |
| `TELEGRAM_CHAT_ID` | `-1003915211068` | ✅ yes |
| `BANKR_API_KEY` | `bk_usr_XB2EnqT7_axHqfJSjhU9U66aKqmdeZcXYfypXRZRA` | recommended |
| `TWITTERAPI_IO_KEY` | `ca8f231ffe57445aa19105689f4eb36e` | recommended |
| `POLL_INTERVAL_S` | `15` | optional |
| `MIN_ETH_AMOUNT` | `0` | optional (whale filter) |
| `MIN_MARKET_CAP_USD` | `0` | optional (whale filter) |

### 4. Deploy
- Railway auto-builds and starts the container.
- Open **Deployments → Logs** — within ~10 s you should see:
  ```
  Bankr Telegram alerter worker started
    Locker contracts: 3
    Telegram chat: -1003915211068
    twitterapi.io: enabled
  Starting from block ... (tip ..., lookback 5)
  ```
- Within a minute or two (whenever the next Bankr claim happens) you'll get
  your Telegram alert.

### 5. Done — Stop the dashboard's own alerter (optional)
If you want to **prevent duplicate alerts** from the Emergent dashboard, set
`TELEGRAM_ENABLED=false` in your Emergent deployment's env vars, redeploy,
and only the Railway worker will send messages.

---

## Alternative: Deploy to Render or Fly.io

Both support the included `Dockerfile` out of the box.

- **Render**: New → Background Worker → connect GitHub → root `worker` → add
  env vars. Free tier sleeps; use the **Starter** plan ($7/mo) for always-on.
- **Fly.io**: `fly launch --dockerfile worker/Dockerfile` from CLI, then
  `fly secrets set TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...`.

---

## Run locally (for testing)

```bash
cd worker
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BANKR_API_KEY, TWITTERAPI_IO_KEY
pip install -r requirements.txt
python main.py
```

> ⚠️ If your Emergent dashboard is also running with its own alerter enabled,
> you'll get **double alerts** from both. Either disable Telegram on the
> dashboard (`TELEGRAM_ENABLED=false`) or stop one of them.

---

## Whale filter

If your channel is getting too many tiny claims, set thresholds:

```
MIN_ETH_AMOUNT=0.05       # only alert when claim ≥ 0.05 ETH
MIN_MARKET_CAP_USD=50000  # ...OR token MC ≥ $50k
```

A claim must pass **at least one** threshold to be alerted. Set both to 0 to
get every claim.
