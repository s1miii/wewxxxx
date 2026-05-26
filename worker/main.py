"""
Bankr Bot — Standalone Telegram Alerter Worker
================================================
Stateless 24/7 worker that watches Base chain for Bankr fee-locker `Released`
events and pushes formatted alerts to Telegram.

This is the SAME indexer logic as the FastAPI backend in `/app/backend/server.py`,
stripped of MongoDB / FastAPI. Designed to run on Railway / Render / Fly.io.

It does NOT write to a database. The Emergent dashboard keeps its own copy.
This worker exists only to guarantee Telegram alerts continue 24/7 even when
the dashboard container is asleep.
"""
from __future__ import annotations

import os
import sys
import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config — all from env
# ---------------------------------------------------------------------------
BASE_RPC_FALLBACKS = [
    os.environ.get("BASE_RPC_URL") or "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
    "https://base.publicnode.com",
    "https://mainnet.base.org",
]
# de-dupe while preserving order
BASE_RPC_FALLBACKS = list(dict.fromkeys([u for u in BASE_RPC_FALLBACKS if u]))

BANKR_API = "https://api.bankr.bot"
BANKR_API_KEY = os.environ.get("BANKR_API_KEY", "")
BANKR_HEADERS = (
    {"Authorization": f"Bearer {BANKR_API_KEY}", "x-api-key": BANKR_API_KEY}
    if BANKR_API_KEY else {}
)

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None
)

TWITTERAPI_IO_KEY = os.environ.get("TWITTERAPI_IO_KEY", "")
TWITTERAPI_IO_BASE = "https://api.twitterapi.io"

# Bankr / Doppler StreamableFeesLocker — Released event
RELEASED_TOPIC = "0x951cb665214ddfa483febb22b592b0c67f38eac40f7be33f6fcbbe63289276d1"
KNOWN_LOCKERS = [
    "0xbdf938149ac6a781f94faa0ed45e6a0e984c6544",
    "0xd59ce43e53d69f190e15d9822fb4540dccc91178",
    "0xa36715da46ddf4a769f3290f49af58bf8132ed8e",
]
WETH_BASE = "0x4200000000000000000000000000000000000006"
ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

POLL_INTERVAL_S = int(os.environ.get("POLL_INTERVAL_S", "15"))
BLOCKS_PER_QUERY = int(os.environ.get("BLOCKS_PER_QUERY", "200"))
# On first boot, only look back this many blocks to avoid re-alerting old claims.
INITIAL_LOOKBACK_BLOCKS = int(os.environ.get("INITIAL_LOOKBACK_BLOCKS", "5"))
DEDUP_CACHE_SIZE = 2000

# Whale filter — only alert if claim meets thresholds (set to 0 to disable)
MIN_ETH_AMOUNT = float(os.environ.get("MIN_ETH_AMOUNT", "0"))
MIN_MARKET_CAP_USD = float(os.environ.get("MIN_MARKET_CAP_USD", "0"))

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bankr-worker")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ETH price (CoinGecko, refreshed every 5 min)
# ---------------------------------------------------------------------------
ETH_PRICE_USD = 3000.0


async def fetch_eth_price(cli: httpx.AsyncClient) -> None:
    global ETH_PRICE_USD
    try:
        r = await cli.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"},
            timeout=8.0,
        )
        if r.status_code == 200:
            ETH_PRICE_USD = float(r.json()["ethereum"]["usd"])
            logger.info(f"ETH price = ${ETH_PRICE_USD}")
    except Exception as e:
        logger.warning(f"ETH price fetch failed: {e}")


async def eth_price_loop(cli: httpx.AsyncClient) -> None:
    while True:
        await fetch_eth_price(cli)
        await asyncio.sleep(300)


# ---------------------------------------------------------------------------
# RPC
# ---------------------------------------------------------------------------
_rpc_idx = 0


async def rpc(method: str, params: list, cli: httpx.AsyncClient, retries: int = 3) -> Any:
    global _rpc_idx
    last_err = None
    for attempt in range(retries):
        url = BASE_RPC_FALLBACKS[_rpc_idx % len(BASE_RPC_FALLBACKS)]
        try:
            r = await cli.post(
                url,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=20.0,
            )
            if r.status_code == 429:
                _rpc_idx += 1
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            d = r.json()
            if "error" in d:
                msg = str(d["error"]).lower()
                if "rate" in msg or "limit" in msg:
                    _rpc_idx += 1
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(f"RPC error: {d['error']}")
            return d["result"]
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last_err = e
            _rpc_idx += 1
            await asyncio.sleep(0.3 * (attempt + 1))
    raise RuntimeError(f"RPC failed after {retries} retries: {last_err}")


async def rpc_unfiltered(method: str, params: list, cli: httpx.AsyncClient,
                          retries: int = 3) -> Any:
    """Pinned to mainnet.base.org for Transfer log queries (no address filter)."""
    url = "https://mainnet.base.org"
    last_err = None
    for attempt in range(retries):
        try:
            r = await cli.post(
                url,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=20.0,
            )
            if r.status_code == 429:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            d = r.json()
            if "error" in d:
                msg = str(d["error"]).lower()
                if "rate" in msg or "limit" in msg:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise RuntimeError(f"RPC error: {d['error']}")
            return d["result"]
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last_err = e
            await asyncio.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"unfiltered RPC failed: {last_err}")


async def get_block_number(cli: httpx.AsyncClient) -> int:
    return int(await rpc("eth_blockNumber", [], cli), 16)


async def get_logs_released(from_block: int, to_block: int,
                             cli: httpx.AsyncClient) -> List[Dict]:
    return await rpc(
        "eth_getLogs",
        [{
            "address": KNOWN_LOCKERS,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "topics": [RELEASED_TOPIC],
        }],
        cli,
    )


async def get_outbound_transfers(from_block: int, to_block: int,
                                  cli: httpx.AsyncClient) -> List[Dict]:
    out: List[Dict] = []
    for locker in KNOWN_LOCKERS:
        padded_from = "0x" + "0" * 24 + locker[2:]
        try:
            logs = await rpc_unfiltered(
                "eth_getLogs",
                [{
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    "topics": [ERC20_TRANSFER_TOPIC, padded_from],
                }],
                cli,
            )
            out.extend(logs)
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.debug(f"transfer logs fail for {locker}: {e}")
    return out


# ---------------------------------------------------------------------------
# Token metadata (on-chain)
# ---------------------------------------------------------------------------
SEL_SYMBOL = "0x95d89b41"
SEL_NAME = "0x06fdde03"
SEL_DECIMALS = "0x313ce567"


def _hex_to_string(h: str) -> str:
    if not h:
        return ""
    h = h.replace("0x", "")
    if len(h) < 128:
        try:
            return bytes.fromhex(h).rstrip(b"\x00").decode("utf-8", errors="ignore")
        except Exception:
            return ""
    try:
        length = int(h[64:128], 16)
        data = h[128:128 + length * 2]
        return bytes.fromhex(data).decode("utf-8", errors="ignore")
    except Exception:
        return ""


# tiny in-memory caches (stateless worker — these reset on container restart)
_token_meta_cache: Dict[str, Dict[str, Any]] = {}
_bankr_creator_cache: Dict[str, Dict[str, Any]] = {}
_x_profile_cache: Dict[str, Dict[str, Any]] = {}
_dexscreener_cache: Dict[str, Dict[str, Any]] = {}


async def fetch_token_meta(addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    addr = addr.lower()
    if addr in _token_meta_cache:
        return _token_meta_cache[addr]
    try:
        sym_raw = await rpc("eth_call", [{"to": addr, "data": SEL_SYMBOL}, "latest"], cli)
        name_raw = await rpc("eth_call", [{"to": addr, "data": SEL_NAME}, "latest"], cli)
        dec_raw = await rpc("eth_call", [{"to": addr, "data": SEL_DECIMALS}, "latest"], cli)
        meta = {
            "symbol": _hex_to_string(sym_raw) or "TOK",
            "name": _hex_to_string(name_raw) or "Unknown",
            "decimals": int(dec_raw, 16) if dec_raw and dec_raw != "0x" else 18,
        }
    except Exception as e:
        logger.debug(f"token meta fail {addr}: {e}")
        meta = {"symbol": "TOK", "name": "Unknown", "decimals": 18}
    _token_meta_cache[addr] = meta
    return meta


async def fetch_bankr_creator(token_addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    token_addr = token_addr.lower()
    if token_addr in _bankr_creator_cache:
        return _bankr_creator_cache[token_addr]
    try:
        r = await cli.get(
            f"{BANKR_API}/token-launches/{token_addr}",
            headers=BANKR_HEADERS, timeout=8.0,
        )
        if r.status_code != 200:
            _bankr_creator_cache[token_addr] = {}
            return {}
        body = r.json() or {}
        launch = body.get("launch") or body
        if not isinstance(launch, dict):
            _bankr_creator_cache[token_addr] = {}
            return {}
        rec = launch.get("feeRecipient") or launch.get("deployer") or {}
        if not rec.get("xUsername") and isinstance(launch.get("deployer"), dict):
            if launch["deployer"].get("xUsername"):
                rec = launch["deployer"]
        handle = rec.get("xUsername")
        out = {
            "handle": handle,
            "avatar": rec.get("xProfileImageUrl"),
            "wallet": (rec.get("walletAddress") or "").lower() or None,
            "tweet_url": launch.get("tweetUrl"),
            "symbol_from_registry": launch.get("tokenSymbol"),
            "name_from_registry": launch.get("tokenName"),
        }
    except Exception as e:
        logger.debug(f"bankr creator fail {token_addr}: {e}")
        out = {}
    _bankr_creator_cache[token_addr] = out
    return out


async def fetch_dexscreener(token_addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    token_addr = token_addr.lower()
    cached = _dexscreener_cache.get(token_addr)
    if cached:
        # cache for 5 minutes within the same worker process
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(cached["_at"])).total_seconds()
        if age < 300:
            return cached
    try:
        r = await cli.get(f"{DEXSCREENER_API}/{token_addr}", timeout=8.0)
        if r.status_code != 200:
            return {}
        body = r.json() or {}
        pairs = body.get("pairs") or []
        if not pairs:
            return {}
        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
                   reverse=True)
        top = pairs[0]
        liq = top.get("liquidity") or {}
        out = {
            "market_cap_usd": float(top.get("marketCap") or 0),
            "fdv_usd": float(top.get("fdv") or 0),
            "liquidity_usd": float(liq.get("usd") or 0),
            "price_usd": float(top.get("priceUsd") or 0),
            "_at": now_iso(),
        }
        _dexscreener_cache[token_addr] = out
        return out
    except Exception as e:
        logger.debug(f"dexscreener fail {token_addr}: {e}")
        return {}


async def fetch_x_profile(username: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    if not username or not TWITTERAPI_IO_KEY:
        return {}
    username = username.strip().lstrip("@")
    key = username.lower()
    cached = _x_profile_cache.get(key)
    if cached:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(cached["_at"])).total_seconds()
        if age < 3600:
            return cached
    try:
        r = await cli.get(
            f"{TWITTERAPI_IO_BASE}/twitter/user/info",
            params={"userName": username},
            headers={"x-api-key": TWITTERAPI_IO_KEY},
            timeout=8.0,
        )
        if r.status_code != 200:
            return cached or {}
        body = r.json()
        if body.get("status") != "success":
            return cached or {}
        data = body.get("data") or {}
        profile = {
            "username": data.get("userName") or username,
            "followers": int(data.get("followers") or 0),
            "is_verified": bool(data.get("isVerified") or data.get("isBlueVerified")),
            "_at": now_iso(),
        }
        _x_profile_cache[key] = profile
        return profile
    except Exception as e:
        logger.debug(f"x_profile fail @{username}: {e}")
        return cached or {}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _esc(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_usd(v: float) -> str:
    v = float(v or 0)
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:.2f}K"
    return f"${v:,.2f}"


def _fmt_amount(v: float, max_dec: int = 4) -> str:
    return f"{float(v or 0):,.{max_dec}f}"


def _fmt_followers(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.1f}K"
    return f"{n}"


def build_message(event: Dict[str, Any]) -> Dict[str, Any]:
    token_addr = event.get("token_address") or ""
    handle = event.get("claimer_handle")
    benef = event.get("beneficiary") or ""
    followers = int(event.get("claimer_followers") or 0)
    verified = bool(event.get("claimer_verified"))
    verified_badge = " ✅" if verified else ""

    if handle:
        if followers > 0:
            handle_str = (
                f"@{_esc(handle)}{verified_badge} · "
                f"<b>{_fmt_followers(followers)}</b> followers"
            )
        else:
            handle_str = f"@{_esc(handle)}{verified_badge}"
        benef_line = f"{handle_str}\n  <code>{_esc(benef)}</code>"
    else:
        benef_line = f"<code>{_esc(benef)}</code>"

    symbol = _esc(event.get("token_symbol") or "?")
    name = _esc(event.get("token_name") or "?")
    tok_amount = _fmt_amount(event.get("released_token_amount") or 0)
    weth_amount = _fmt_amount(event.get("released_weth_amount") or 0, max_dec=6)
    usd_amount = _fmt_usd(event.get("released_usd") or 0)
    mc = _fmt_usd(event.get("market_cap_usd") or 0)
    liq = _fmt_usd(event.get("liquidity_usd") or 0)

    text = (
        "🎉 <b>NEW BANKR FEE CLAIMED!</b>\n\n"
        "<b>Token Information:</b>\n"
        f"• Name: <b>{name}</b>\n"
        f"• Symbol: <b>${symbol}</b>\n"
        f"• Contract: <code>{_esc(token_addr)}</code>\n"
        f"• Market Cap: <b>{mc}</b>\n"
        f"• Liquidity: <b>{liq}</b>\n\n"
        "<b>Released to Beneficiary:</b>\n"
        f"• Token Amount: <b>{tok_amount} ${symbol}</b>\n"
        f"• ETH Amount: <b>{weth_amount} ETH</b> ({usd_amount})\n"
        f"• Beneficiary: {benef_line}"
    )

    keyboard: List[List[Dict[str, str]]] = []
    if token_addr:
        keyboard.append([
            {"text": "🚀 Bankr Launch", "url": f"https://bankr.bot/launches/{token_addr}"},
        ])
        keyboard.append([
            {"text": "💰 Buy",
             "url": f"https://t.me/based_rescue_bot?start=r_botprivacy_b_{token_addr}"},
        ])
        keyboard.append([
            {"text": "🔍 Search on X",
             "url": f"https://twitter.com/search?q={token_addr}"},
        ])
    if handle:
        flw = f" · {_fmt_followers(followers)} followers" if followers > 0 else ""
        keyboard.append([
            {"text": f"𝕏 Beneficiary @{handle}{flw}",
             "url": f"https://twitter.com/{handle}"},
        ])

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def send_telegram(event: Dict[str, Any], cli: httpx.AsyncClient) -> bool:
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping alert")
        return False
    try:
        msg = build_message(event)
        r = await cli.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg["text"],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": msg["reply_markup"],
            },
            timeout=10.0,
        )
        if r.status_code == 200 and r.json().get("ok"):
            return True
        logger.warning(f"telegram send failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        logger.warning(f"telegram exception: {e}")
    return False


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------
def _build_transfer_index(transfers: List[Dict]) -> Dict[str, List[Dict]]:
    idx: Dict[str, List[Dict]] = {}
    for log in transfers:
        idx.setdefault(log["transactionHash"], []).append(log)
    return idx


def find_token_from_transfers(tx_transfers: List[Dict], locker: str,
                               beneficiary: str) -> Optional[str]:
    locker_l = locker.lower()
    benef_l = beneficiary.lower()
    for log in tx_transfers:
        if len(log.get("topics") or []) < 3:
            continue
        frm = "0x" + log["topics"][1][-40:].lower()
        to = "0x" + log["topics"][2][-40:].lower()
        tok = log["address"].lower()
        if frm == locker_l and to == benef_l and tok != WETH_BASE.lower():
            return tok
    return None


async def process_released(log: Dict[str, Any], tx_transfers: List[Dict[str, Any]],
                            cli: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    tx_hash = log["transactionHash"]
    log_index = int(log["logIndex"], 16)
    locker = log["address"].lower()
    beneficiary = "0x" + log["topics"][2][-40:].lower()
    data = log["data"].replace("0x", "")
    amt0_raw = int(data[0:64], 16) if len(data) >= 64 else 0
    amt1_raw = int(data[64:128], 16) if len(data) >= 128 else 0

    if amt0_raw == 0 and amt1_raw == 0:
        return None

    token_addr = find_token_from_transfers(tx_transfers, locker, beneficiary)

    # Determine which leg is token vs WETH
    token_amount_raw = amt0_raw
    weth_amount_raw = amt1_raw
    if token_addr:
        if int(token_addr, 16) > int(WETH_BASE, 16):
            token_amount_raw, weth_amount_raw = amt1_raw, amt0_raw
    else:
        WETH_CAP_RAW = 10 ** 21
        if amt0_raw > WETH_CAP_RAW and amt1_raw <= WETH_CAP_RAW:
            token_amount_raw, weth_amount_raw = amt0_raw, amt1_raw
        elif amt1_raw > WETH_CAP_RAW and amt0_raw <= WETH_CAP_RAW:
            token_amount_raw, weth_amount_raw = amt1_raw, amt0_raw

    weth_amount = weth_amount_raw / 1e18

    # Token meta — Bankr registry first, then on-chain
    token_symbol = "?"
    token_name = "?"
    token_decimals = 18
    creator: Dict[str, Any] = {}
    if token_addr:
        creator = await fetch_bankr_creator(token_addr, cli)
        if creator.get("symbol_from_registry"):
            token_symbol = creator["symbol_from_registry"]
            token_name = creator.get("name_from_registry") or "?"
        meta = await fetch_token_meta(token_addr, cli)
        if token_symbol in ("?", "TOK", None) and meta.get("symbol"):
            token_symbol = meta["symbol"]
        if token_name in ("?", "Unknown", None) and meta.get("name"):
            token_name = meta["name"]
        token_decimals = int(meta.get("decimals") or 18)

    token_amount = token_amount_raw / (10 ** token_decimals) if token_addr else 0
    claimer_handle = creator.get("handle")

    x_profile = await fetch_x_profile(claimer_handle, cli) if claimer_handle else {}

    market_cap_usd = 0.0
    liquidity_usd = 0.0
    if token_addr:
        ds = await fetch_dexscreener(token_addr, cli)
        market_cap_usd = ds.get("market_cap_usd") or ds.get("fdv_usd") or 0
        liquidity_usd = ds.get("liquidity_usd") or 0

    return {
        "tx_hash": tx_hash,
        "log_index": log_index,
        "token_address": token_addr,
        "token_symbol": token_symbol,
        "token_name": token_name,
        "beneficiary": beneficiary,
        "claimer_handle": claimer_handle,
        "claimer_followers": int(x_profile.get("followers") or 0),
        "claimer_verified": bool(x_profile.get("is_verified")),
        "released_token_amount": token_amount,
        "released_weth_amount": weth_amount,
        "released_usd": round(weth_amount * ETH_PRICE_USD, 2),
        "market_cap_usd": market_cap_usd,
        "liquidity_usd": liquidity_usd,
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
async def indexer_loop(cli: httpx.AsyncClient) -> None:
    logger.info("Bankr Telegram alerter worker started")
    logger.info(f"  Locker contracts: {len(KNOWN_LOCKERS)}")
    logger.info(f"  Telegram chat: {TELEGRAM_CHAT_ID or '<NOT SET>'}")
    logger.info(f"  twitterapi.io: {'enabled' if TWITTERAPI_IO_KEY else 'disabled'}")
    logger.info(f"  Whale filter: ETH≥{MIN_ETH_AMOUNT} or MC≥${MIN_MARKET_CAP_USD:,.0f}")

    tip = await get_block_number(cli)
    last_block = max(0, tip - INITIAL_LOOKBACK_BLOCKS)
    logger.info(f"Starting from block {last_block} (tip {tip}, lookback {INITIAL_LOOKBACK_BLOCKS})")

    seen: deque = deque(maxlen=DEDUP_CACHE_SIZE)
    seen_set: set = set()

    while True:
        try:
            tip = await get_block_number(cli)
            if last_block >= tip:
                await asyncio.sleep(POLL_INTERVAL_S)
                continue
            from_block = last_block + 1
            to_block = min(tip, from_block + BLOCKS_PER_QUERY - 1)

            released = await get_logs_released(from_block, to_block, cli)
            transfers = await get_outbound_transfers(from_block, to_block, cli) if released else []
            tx_idx = _build_transfer_index(transfers)

            alerts_sent = 0
            for log in released:
                key = f"{log['transactionHash']}-{int(log['logIndex'], 16)}"
                if key in seen_set:
                    continue
                seen.append(key)
                if len(seen) == DEDUP_CACHE_SIZE:
                    # cheap eviction: rebuild set from deque every cycle
                    pass
                seen_set = set(seen)

                event = await process_released(
                    log, tx_idx.get(log["transactionHash"], []), cli
                )
                if not event:
                    continue
                if event["released_weth_amount"] <= 0:
                    continue

                # Whale filter
                if MIN_ETH_AMOUNT > 0 and event["released_weth_amount"] < MIN_ETH_AMOUNT:
                    if MIN_MARKET_CAP_USD <= 0 or event["market_cap_usd"] < MIN_MARKET_CAP_USD:
                        logger.info(
                            f"SKIP (filter): @{event['claimer_handle'] or '???'} "
                            f"{event['released_weth_amount']:.6f} ETH "
                            f"MC ${event['market_cap_usd']:,.0f}"
                        )
                        continue

                ok = await send_telegram(event, cli)
                alerts_sent += 1 if ok else 0
                logger.info(
                    f"{'SENT' if ok else 'FAIL'} @{event['claimer_handle'] or '???'} "
                    f"got {event['released_token_amount']:.4f} ${event['token_symbol']} "
                    f"+ {event['released_weth_amount']:.6f} ETH "
                    f"(MC ${event['market_cap_usd']:,.0f}) tx={log['transactionHash'][:12]}"
                )

            if released:
                logger.info(
                    f"blocks {from_block}-{to_block}: {len(released)} released, "
                    f"{alerts_sent} TG alerts"
                )
            last_block = to_block

            # Sleep proportional to how close we are to the tip
            if to_block >= tip - 5:
                await asyncio.sleep(POLL_INTERVAL_S)
        except Exception as e:
            logger.error(f"indexer loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL_S)


async def main() -> None:
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
        sys.exit(1)

    async with httpx.AsyncClient() as cli:
        await fetch_eth_price(cli)
        await asyncio.gather(
            eth_price_loop(cli),
            indexer_loop(cli),
        )


if __name__ == "__main__":
    asyncio.run(main())
