# BANKR.SCAN — Bankr Bot Claim Fee Monitor

## Problem Statement
> "i want build claim fee bankrbot monitoring , can you build ? this docs https://docs.bankr.bot/ and i want detect twitter username who claim fee"

Build a monitoring dashboard that detects Twitter/X usernames who claim trading fees
from Bankr-launched tokens on Base.

## User Choices
- Chain: **Base** only
- Feature: Live feed of claim events
- Data: Public RPC + mock/seed data + Bankr public API enrichment
- Design: Defaults (terminal/neon aesthetic chosen by design agent)

## Architecture
- **Backend**: FastAPI + MongoDB (motor). Background asyncio poller every 15s injects realistic claim events
  enriched with Bankr public API (`api.bankr.bot/token-launches/{addr}/fees`). ETH price polled from CoinGecko.
- **Frontend**: React + react-router + recharts + sonner. Tailwind + custom CSS for terminal/neon look.

## Personas
- **Onchain analyst** — watches who's pulling fees from the Bankr flywheel
- **Token launcher** — tracks own claim history per token
- **Researcher** — looks up top claimers by X handle

## Core Requirements
1. Live feed of claim events showing X handle, token, ETH amount, USD value, tx link to Basescan
2. KPI strip (Total Claims, Total ETH, Unique Claimers, 24h Volume)
3. Top claimers leaderboard ranked by ETH claimed
4. Token tracking (add new Base token by address)
5. Token detail page with 14d daily claim chart + recent claims
6. Claimer (X handle) detail page with all-time claim history

## Implemented (2026-05-26)
- [x] Backend: `/api/stats`, `/api/claims/feed`, `/api/leaderboard`, `/api/tokens`,
      `/api/tokens/{address}`, `/api/tokens/track`, `/api/search`, `/api/handle/{handle}`
- [x] Background poller (15s tick) + seed: 10 Bankr tokens, 15 X handles, 120 historical events
- [x] ETH price from CoinGecko
- [x] Bankr public API integration (read-only fees endpoint)
- [x] Frontend: Dashboard, TokensPage, TokenDetail, LeaderboardPage, ClaimerDetail
- [x] Terminal/neon design (Azeret Mono + IBM Plex Mono, void black + neon green/cyan/yellow/pink)
- [x] Live auto-refresh (feed every 6s, stats every 8s, leaderboard every 12s)
- [x] Filters (by handle prefix, by token symbol)
- [x] Add-token form with Bankr API enrichment
- [x] 100% test pass (17/17 backend, full frontend e2e)

## Backlog
### P1
- [ ] Real on-chain event listener (Doppler/Clanker fee-claim event signatures via Base RPC)
- [ ] Twitter API integration to verify handle resolution (Bankr stores X handle on-chain)
- [ ] WebSocket push instead of polling
- [ ] Per-token watchlist / alerts

### P2
- [ ] Multi-chain support (Solana via Helius)
- [ ] CSV export of claim history
- [ ] Discord/Telegram webhook alerts
- [ ] Sparkline mini-charts in leaderboard
- [ ] DB indexes for production scale (claim_events.timestamp, token_address)
- [ ] Migrate to FastAPI lifespan context manager

## Next Tasks
- Hook a real on-chain event source once user provides RPC/Alchemy key
- Resolve Twitter handles via Bankr `/token-launches/{addr}/fees` `creator.xUsername` field
