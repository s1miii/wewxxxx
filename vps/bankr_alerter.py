"""
Bankr Bot Telegram Alerter — single-file VPS worker (no .env)
=============================================================
Edit the CONFIG block below with your secrets, then run:

    pip install httpx
    python3 bankr_alerter.py

FIXED: prevents duplicate Telegram messages by
  1) acquiring an exclusive file lock so only ONE instance can run
  2) persisting de-dup keys + last processed block to disk
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

# ===========================================================
# CONFIG — EDIT HERE
# ===========================================================
BANKR_API_KEY      = "bk_usr_XB2EnqT7_axHqfJSjhU9U66aKqmdeZcXYfypXRZRA"
TELEGRAM_BOT_TOKEN = "8335281387:AAH5KfMmXgtkhERBtCEeQsCbraA6zEvr30w"
TELEGRAM_CHAT_ID   = "-1003915211068"

# How often to poll the chain (seconds)
POLL_INTERVAL_S = 5

# On first start, look back this many blocks (keep small to avoid old alerts)
INITIAL_LOOKBACK_BLOCKS = 5

# Whale filter — set both to 0 to alert on ALL claims
MIN_ETH_AMOUNT       = 0     # only alert when claim >= this ETH amount
MIN_MARKET_CAP_USD   = 0     # ...OR when token MC >= this USD

# Persistent state / lock files (kept next to this script)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bankr_state.json")
LOCK_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bankr_alerter.lock")
# ===========================================================

TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BANKR_HEADERS  = ({"Authorization": f"Bearer {BANKR_API_KEY}",
                   "x-api-key": BANKR_API_KEY} if BANKR_API_KEY else {})

BASE_RPC_FALLBACKS = [
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
    "https://base.publicnode.com",
    "https://mainnet.base.org",
]
BANKR_API       = "https://api.bankr.bot"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
RELEASED_TOPIC  = "0x951cb665214ddfa483febb22b592b0c67f38eac40f7be33f6fcbbe63289276d1"
KNOWN_LOCKERS   = [
    "0xbdf938149ac6a781f94faa0ed45e6a0e984c6544",
    "0xd59ce43e53d69f190e15d9822fb4540dccc91178",
    "0xa36715da46ddf4a769f3290f49af58bf8132ed8e",
]
WETH_BASE              = "0x4200000000000000000000000000000000000006"
ERC20_TRANSFER_TOPIC   = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("bankr")

_token_cache: Dict[str, Dict[str, Any]] = {}
_bankr_cache: Dict[str, Dict[str, Any]] = {}
_ds_cache:    Dict[str, Dict[str, Any]] = {}
ETH_PRICE_USD = 3000.0

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------- Single-instance lock ----------
def acquire_single_instance_lock() -> Any:
    """
    Acquire an exclusive, non-blocking file lock. If another instance of
    this script is already running, exit immediately with a clear message.
    This is the #1 cause of duplicate Telegram messages.
    """
    try:
        import fcntl  # POSIX only (Linux VPS)
    except ImportError:
        log.warning("fcntl not available; skipping single-instance lock (Windows?)")
        return None

    fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error(
            "Another instance of bankr_alerter.py is already running "
            f"(lock file: {LOCK_FILE}). "
            "Refusing to start to avoid duplicate Telegram messages."
        )
        sys.exit(1)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh  # keep open for the lifetime of the process

# ---------- Persistent state ----------
def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.warning(f"Failed to load state: {e}")
        return {}

def save_state(last_block: int, seen_keys: List[str]) -> None:
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"last_block": last_block, "seen": seen_keys[-2000:]}, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log.warning(f"Failed to save state: {e}")

# ---------- RPC ----------
_rpc_idx = 0

async def rpc(method: str, params: list, cli: httpx.AsyncClient,
              retries: int = 3, fixed_url: Optional[str] = None) -> Any:
    global _rpc_idx
    last_err = None
    for attempt in range(retries):
        url = fixed_url or BASE_RPC_FALLBACKS[_rpc_idx % len(BASE_RPC_FALLBACKS)]
        try:
            r = await cli.post(url, json={
                "jsonrpc": "2.0", "method": method, "params": params, "id": 1,
            }, timeout=20.0)
            if r.status_code == 429:
                _rpc_idx += 1
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            d = r.json()
            if "error" in d:
                msg = str(d["error"]).lower()
                if "rate" in msg or "limit" in msg:
                    _rpc_idx += 1
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise RuntimeError(d["error"])
            return d["result"]
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last_err = e
            _rpc_idx += 1
            await asyncio.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"RPC failed: {last_err}")

async def get_block_number(cli: httpx.AsyncClient) -> int:
    return int(await rpc("eth_blockNumber", [], cli), 16)

async def get_released_logs(from_b: int, to_b: int,
                            cli: httpx.AsyncClient) -> List[Dict]:
    return await rpc("eth_getLogs", [{
        "address": KNOWN_LOCKERS,
        "fromBlock": hex(from_b),
        "toBlock":   hex(to_b),
        "topics":    [RELEASED_TOPIC],
    }], cli)

async def get_outbound_transfers(from_b: int, to_b: int,
                                 cli: httpx.AsyncClient) -> List[Dict]:
    out: List[Dict] = []
    for locker in KNOWN_LOCKERS:
        padded = "0x" + "0" * 24 + locker[2:]
        try:
            logs = await rpc("eth_getLogs", [{
                "fromBlock": hex(from_b),
                "toBlock":   hex(to_b),
                "topics":    [ERC20_TRANSFER_TOPIC, padded],
            }], cli, fixed_url="https://mainnet.base.org")
            out.extend(logs)
            await asyncio.sleep(0.15)
        except Exception as e:
            log.debug(f"transfer logs fail {locker}: {e}")
    return out

# ---------- Metadata ----------
SEL_SYMBOL   = "0x95d89b41"
SEL_NAME     = "0x06fdde03"
SEL_DECIMALS = "0x313ce567"

def _hex_to_string(h: str) -> str:
    if not h:
        return ""
    h = h.replace("0x", "")
    if len(h) < 128:
        try:
            return bytes.fromhex(h).rstrip(b"\0").decode("utf-8", errors="ignore")
        except Exception:
            return ""
    try:
        length = int(h[64:128], 16)
        return bytes.fromhex(h[128:128 + length * 2]).decode("utf-8", errors="ignore")
    except Exception:
        return ""

async def fetch_token_meta(addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    addr = addr.lower()
    if addr in _token_cache:
        return _token_cache[addr]
    try:
        sym  = await rpc("eth_call", [{"to": addr, "data": SEL_SYMBOL},   "latest"], cli)
        name = await rpc("eth_call", [{"to": addr, "data": SEL_NAME},     "latest"], cli)
        dec  = await rpc("eth_call", [{"to": addr, "data": SEL_DECIMALS}, "latest"], cli)
        meta = {
            "symbol":   _hex_to_string(sym)  or "TOK",
            "name":     _hex_to_string(name) or "Unknown",
            "decimals": int(dec, 16) if dec and dec != "0x" else 18,
        }
    except Exception as e:
        log.debug(f"meta fail {addr}: {e}")
        meta = {"symbol": "TOK", "name": "Unknown", "decimals": 18}
    _token_cache[addr] = meta
    return meta

async def fetch_bankr_creator(token_addr: str,
                              cli: httpx.AsyncClient) -> Dict[str, Any]:
    token_addr = token_addr.lower()
    if token_addr in _bankr_cache:
        return _bankr_cache[token_addr]
    try:
        r = await cli.get(f"{BANKR_API}/token-launches/{token_addr}",
                          headers=BANKR_HEADERS, timeout=8.0)
        if r.status_code != 200:
            _bankr_cache[token_addr] = {}
            return {}
        body = r.json() or {}
        launch = body.get("launch") or body
        if not isinstance(launch, dict):
            _bankr_cache[token_addr] = {}
            return {}
        rec = launch.get("feeRecipient") or launch.get("deployer") or {}
        if not rec.get("xUsername") and isinstance(launch.get("deployer"), dict):
            if launch["deployer"].get("xUsername"):
                rec = launch["deployer"]
        out = {
            "handle": rec.get("xUsername"),
            "symbol": launch.get("tokenSymbol"),
            "name":   launch.get("tokenName"),
        }
    except Exception as e:
        log.debug(f"bankr fail {token_addr}: {e}")
        out = {}
    _bankr_cache[token_addr] = out
    return out

async def fetch_dexscreener(token_addr: str,
                            cli: httpx.AsyncClient) -> Dict[str, Any]:
    token_addr = token_addr.lower()
    cached = _ds_cache.get(token_addr)
    if cached and (datetime.now(timezone.utc)
                   - datetime.fromisoformat(cached["_at"])
                   ).total_seconds() < 300:
        return cached
    try:
        r = await cli.get(f"{DEXSCREENER_API}/{token_addr}", timeout=8.0)
        if r.status_code != 200:
            return {}
        pairs = (r.json() or {}).get("pairs") or []
        if not pairs:
            return {}
        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
                   reverse=True)
        top = pairs[0]
        out = {
            "market_cap_usd": float(top.get("marketCap") or 0),
            "fdv_usd":        float(top.get("fdv") or 0),
            "liquidity_usd":  float((top.get("liquidity") or {}).get("usd") or 0),
            "_at": now_iso(),
        }
        _ds_cache[token_addr] = out
        return out
    except Exception as e:
        log.debug(f"dexscreener fail {token_addr}: {e}")
        return {}

async def fetch_eth_price(cli: httpx.AsyncClient) -> None:
    global ETH_PRICE_USD
    try:
        r = await cli.get("https://api.coingecko.com/api/v3/simple/price",
                          params={"ids": "ethereum", "vs_currencies": "usd"},
                          timeout=8.0)
        if r.status_code == 200:
            ETH_PRICE_USD = float(r.json()["ethereum"]["usd"])
            log.info(f"ETH price = ${ETH_PRICE_USD}")
    except Exception as e:
        log.warning(f"ETH price fetch failed: {e}")

async def eth_price_loop(cli: httpx.AsyncClient) -> None:
    while True:
        await fetch_eth_price(cli)
        await asyncio.sleep(300)

# ---------- Formatting ----------
def _esc(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _fmt_usd(v: float) -> str:
    v = float(v or 0)
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    if v >= 1e3:
        return f"${v/1e3:.2f}K"
    return f"${v:,.2f}"

def _fmt_amount(v: float, max_dec: int = 4) -> str:
    return f"{float(v or 0):,.{max_dec}f}"

def build_message(e: Dict[str, Any]) -> Dict[str, Any]:
    token_addr = e.get("token_address") or ""
    handle     = e.get("claimer_handle")
    benef      = e.get("beneficiary") or ""
    symbol     = _esc(e.get("token_symbol") or "?")
    name       = _esc(e.get("token_name") or "?")

    if handle:
        benef_line = f"@{_esc(handle)}\n  <code>{_esc(benef)}</code>"
    else:
        benef_line = f"<code>{_esc(benef)}</code>"

    text = (
        "🎉 <b>NEW BANKR FEE CLAIMED!</b>\n\n"
        " <b>Token Information:</b>\n"
        f"• Name: <b>{name}</b>\n"
        f"• Symbol: <b>${symbol}</b>\n"
        f"• Contract: <code>{_esc(token_addr)}</code>\n"
        f"• Market Cap: <b>{_fmt_usd(e.get('market_cap_usd') or 0)}</b>\n"
        f"• Liquidity:  <b>{_fmt_usd(e.get('liquidity_usd') or 0)}</b>\n\n"
        " <b>Released to Beneficiary:</b>\n"
        f"• Token Amount: <b>{_fmt_amount(e.get('released_token_amount') or 0)} ${symbol}</b>\n"
        f"• ETH Amount:   <b>{_fmt_amount(e.get('released_weth_amount') or 0, 6)} ETH</b> "
        f"({_fmt_usd(e.get('released_usd') or 0)})\n"
        f"• Beneficiary:  {benef_line}"
    )

    kb: List[List[Dict[str, str]]] = []
    if token_addr:
        kb.append([{"text": "🚀 Bankr Launch", "url": f"https://bankr.bot/launches/{token_addr}"}])
        kb.append([{"text": "💰 Buy",          "url": f"https://t.me/based_rescue_bot?start=r_botprivacy_b_{token_addr}"}])
        kb.append([{"text": "📈 GMGN",         "url": f"https://gmgn.ai/base/token/{token_addr}"}])
        kb.append([{"text": "🔍 Search on X",  "url": f"https://twitter.com/search?q={token_addr}"}])
    if handle:
        kb.append([{"text": f"𝕏 Beneficiary @{handle}", "url": f"https://twitter.com/{handle}"}])

    return {"text": text, "reply_markup": {"inline_keyboard": kb}}

async def send_telegram(event: Dict[str, Any], cli: httpx.AsyncClient) -> bool:
    msg = build_message(event)
    try:
        r = await cli.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text":    msg["text"],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": msg["reply_markup"],
        }, timeout=10.0)
        if r.status_code == 200 and r.json().get("ok"):
            return True
        log.warning(f"telegram failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"telegram exception: {e}")
    return False

# ---------- Event processing ----------
def _idx_transfers(transfers: List[Dict]) -> Dict[str, List[Dict]]:
    idx: Dict[str, List[Dict]] = {}
    for t in transfers:
        idx.setdefault(t["transactionHash"], []).append(t)
    return idx

def find_token(tx_transfers: List[Dict], locker: str,
               beneficiary: str) -> Optional[str]:
    locker_l, benef_l = locker.lower(), beneficiary.lower()
    for t in tx_transfers:
        if len(t.get("topics") or []) < 3:
            continue
        frm = "0x" + t["topics"][1][-40:].lower()
        to  = "0x" + t["topics"][2][-40:].lower()
        tok = t["address"].lower()
        if frm == locker_l and to == benef_l and tok != WETH_BASE.lower():
            return tok
    return None

async def process_event(entry: Dict[str, Any], tx_transfers: List[Dict[str, Any]],
                        cli: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    locker      = entry["address"].lower()
    beneficiary = "0x" + entry["topics"][2][-40:].lower()
    data        = entry["data"].replace("0x", "")
    amt0        = int(data[0:64],   16) if len(data) >= 64  else 0
    amt1        = int(data[64:128], 16) if len(data) >= 128 else 0

    if amt0 == 0 and amt1 == 0:
        return None

    token_addr = find_token(tx_transfers, locker, beneficiary)

    tok_raw, weth_raw = amt0, amt1
    if token_addr:
        if int(token_addr, 16) > int(WETH_BASE, 16):
            tok_raw, weth_raw = amt1, amt0
    else:
        WETH_CAP = 10 ** 21
        if   amt0 > WETH_CAP and amt1 <= WETH_CAP:
            tok_raw, weth_raw = amt0, amt1
        elif amt1 > WETH_CAP and amt0 <= WETH_CAP:
            tok_raw, weth_raw = amt1, amt0

    weth_amount    = weth_raw / 1e18
    token_symbol   = "?"
    token_name     = "?"
    token_decimals = 18
    creator: Dict[str, Any] = {}

    if token_addr:
        creator = await fetch_bankr_creator(token_addr, cli)
        if creator.get("symbol"):
            token_symbol = creator["symbol"]
            token_name   = creator.get("name") or "?"
        meta = await fetch_token_meta(token_addr, cli)
        if token_symbol in ("?", "TOK") and meta.get("symbol"):
            token_symbol = meta["symbol"]
        if token_name in ("?", "Unknown") and meta.get("name"):
            token_name = meta["name"]
        token_decimals = int(meta.get("decimals") or 18)

    token_amount = tok_raw / (10 ** token_decimals) if token_addr else 0

    market_cap = liquidity = 0.0
    if token_addr:
        ds = await fetch_dexscreener(token_addr, cli)
        market_cap = ds.get("market_cap_usd") or ds.get("fdv_usd") or 0
        liquidity  = ds.get("liquidity_usd") or 0

    return {
        "token_address":          token_addr,
        "token_symbol":           token_symbol,
        "token_name":             token_name,
        "beneficiary":            beneficiary,
        "claimer_handle":         creator.get("handle"),
        "released_token_amount":  token_amount,
        "released_weth_amount":   weth_amount,
        "released_usd":           round(weth_amount * ETH_PRICE_USD, 2),
        "market_cap_usd":         market_cap,
        "liquidity_usd":          liquidity,
    }

# ---------- Main loop ----------
async def indexer_loop(cli: httpx.AsyncClient) -> None:
    log.info("Bankr Telegram alerter started")
    log.info(f"  Telegram chat: {TELEGRAM_CHAT_ID}")
    log.info(f"  Whale filter:  ETH>={MIN_ETH_AMOUNT}  MC>=${MIN_MARKET_CAP_USD:,.0f}")

    state = load_state()
    tip = await get_block_number(cli)

    saved_last = state.get("last_block")
    if isinstance(saved_last, int) and saved_last > 0:
        # Resume from where we left off; cap to tip to avoid huge backfills.
        last_block = min(saved_last, tip)
        log.info(f"Resuming from persisted block {last_block} (tip {tip})")
    else:
        last_block = max(0, tip - INITIAL_LOOKBACK_BLOCKS)
        log.info(f"Starting fresh from block {last_block} (tip {tip})")

    saved_seen = state.get("seen") or []
    seen_deque: deque = deque(saved_seen, maxlen=2000)
    seen_set: set = set(seen_deque)

    while True:
        try:
            tip = await get_block_number(cli)
            if last_block >= tip:
                await asyncio.sleep(POLL_INTERVAL_S)
                continue
            from_b = last_block + 1
            to_b   = min(tip, from_b + 200 - 1)

            released  = await get_released_logs(from_b, to_b, cli)
            transfers = await get_outbound_transfers(from_b, to_b, cli) if released else []
            tx_idx    = _idx_transfers(transfers)

            alerts = 0
            for entry in released:
                key = f"{entry['transactionHash']}-{int(entry['logIndex'], 16)}"
                if key in seen_set:
                    continue

                # Mark as seen BEFORE sending so retries/crashes never resend.
                if len(seen_deque) == seen_deque.maxlen:
                    seen_set.discard(seen_deque[0])
                seen_deque.append(key)
                seen_set.add(key)

                event = await process_event(
                    entry, tx_idx.get(entry["transactionHash"], []), cli,
                )
                if not event or event["released_weth_amount"] <= 0:
                    # Still persist seen so we don't reconsider it on restart.
                    save_state(last_block, list(seen_deque))
                    continue

                if MIN_ETH_AMOUNT > 0 or MIN_MARKET_CAP_USD > 0:
                    passes_eth = event["released_weth_amount"] >= MIN_ETH_AMOUNT
                    passes_mc  = event["market_cap_usd"]       >= MIN_MARKET_CAP_USD
                    if not (passes_eth or passes_mc):
                        log.info(
                            f"SKIP (filter): @{event['claimer_handle'] or '???'} "
                            f"{event['released_weth_amount']:.6f} ETH "
                            f"MC ${event['market_cap_usd']:,.0f}"
                        )
                        save_state(last_block, list(seen_deque))
                        continue

                ok = await send_telegram(event, cli)
                alerts += 1 if ok else 0
                log.info(
                    f"{'SENT' if ok else 'FAIL'} @{event['claimer_handle'] or '???'} "
                    f"{event['released_token_amount']:.4f} ${event['token_symbol']} "
                    f"+ {event['released_weth_amount']:.6f} ETH "
                    f"(MC ${event['market_cap_usd']:,.0f}) "
                    f"tx={entry['transactionHash'][:12]}"
                )

                # Persist after every alert so a crash never causes a re-send.
                save_state(last_block, list(seen_deque))

            if released:
                log.info(f"blocks {from_b}-{to_b}: "
                         f"{len(released)} released, {alerts} alerts sent")

            last_block = to_b
            save_state(last_block, list(seen_deque))

            if to_b >= tip - 5:
                await asyncio.sleep(POLL_INTERVAL_S)
        except Exception as e:
            log.error(f"loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL_S)

async def main() -> None:
    if "PASTE_" in TELEGRAM_BOT_TOKEN or "PASTE_" in TELEGRAM_CHAT_ID:
        log.error("Please edit the CONFIG block at the top of this file "
                  "with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        sys.exit(1)
    async with httpx.AsyncClient() as cli:
        await fetch_eth_price(cli)
        await asyncio.gather(eth_price_loop(cli), indexer_loop(cli))

if __name__ == "__main__":
    # Ensure only ONE instance is ever running on this machine.
    _lock_fh = acquire_single_instance_lock()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("shutting down")
