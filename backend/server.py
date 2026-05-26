from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import httpx
from pathlib import Path
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bankr-monitor")

app = FastAPI(title="Bankr Bot Claim Fee Monitor")
api_router = APIRouter(prefix="/api")


# ============================================================
# CONFIG
# ============================================================
BASE_RPC = os.environ.get("BASE_RPC_URL", "https://base-rpc.publicnode.com")
BASE_RPC_FALLBACKS = [
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
    "https://base.publicnode.com",
    "https://mainnet.base.org",
]
BANKR_API = "https://api.bankr.bot"
BANKR_API_KEY = os.environ.get("BANKR_API_KEY", "")
BANKR_HEADERS = (
    {"Authorization": f"Bearer {BANKR_API_KEY}", "x-api-key": BANKR_API_KEY}
    if BANKR_API_KEY else {}
)
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

# Telegram alerting
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "true").lower() in ("1", "true", "yes")
TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None
)
TELEGRAM_LIVE_BLOCK_THRESHOLD = 50

# twitterapi.io — for fetching X profile (followers count)
TWITTERAPI_IO_KEY = os.environ.get("TWITTERAPI_IO_KEY", "")
TWITTERAPI_IO_BASE = "https://api.twitterapi.io"
X_PROFILE_TTL_SECONDS = 3600  # cache profiles for 1h to avoid burning credits

# Bankr / Doppler StreamableFeesLocker — RELEASED event topic
# event Released(bytes32 indexed streamId, address indexed beneficiary,
#                uint256 token0Amount, uint256 token1Amount)
RELEASED_TOPIC = "0x951cb665214ddfa483febb22b592b0c67f38eac40f7be33f6fcbbe63289276d1"
# Known Bankr / Doppler StreamableFeesLocker contracts (multiple instances exist).
# We filter by these + by topic for both performance and to match RPC providers
# that require an address filter (e.g. publicnode).
KNOWN_LOCKERS = [
    "0xbdf938149ac6a781f94faa0ed45e6a0e984c6544",
    "0xd59ce43e53d69f190e15d9822fb4540dccc91178",  # user-requested
    "0xa36715da46ddf4a769f3290f49af58bf8132ed8e",
]
WETH_BASE = "0x4200000000000000000000000000000000000006"
POOL_MANAGER = "0x498581ff718922c3f8e6a244956af099b2652b2b"
ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

POLL_INTERVAL_S = int(os.environ.get("POLL_INTERVAL_S", "15"))
BLOCKS_PER_QUERY = 4000
INITIAL_BACKFILL_BLOCKS = int(os.environ.get("INITIAL_BACKFILL_BLOCKS", "20000"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# ETH PRICE
# ============================================================
ETH_PRICE_USD = 3000.0


async def fetch_eth_price() -> float:
    global ETH_PRICE_USD
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
            )
            ETH_PRICE_USD = float(r.json()["ethereum"]["usd"])
            logger.info(f"ETH price = ${ETH_PRICE_USD}")
    except Exception as e:
        logger.warning(f"ETH price fetch failed: {e}")
    return ETH_PRICE_USD


# ============================================================
# RPC HELPERS
# ============================================================
_rpc_idx = 0


async def rpc(method: str, params: list, cli: httpx.AsyncClient, retries: int = 3) -> Any:
    """RPC with rotating endpoint fallback + exponential backoff on 429."""
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
        except (httpx.HTTPError, httpx.ConnectError, asyncio.TimeoutError) as e:
            last_err = e
            _rpc_idx += 1
            await asyncio.sleep(0.3 * (attempt + 1))
            continue
    raise RuntimeError(f"RPC failed after {retries} retries: {last_err}")


async def get_block_number(cli: httpx.AsyncClient) -> int:
    return int(await rpc("eth_blockNumber", [], cli), 16)


async def get_block_timestamp(block_hex: str, cli: httpx.AsyncClient) -> int:
    blk = await rpc("eth_getBlockByNumber", [block_hex, False], cli)
    return int(blk["timestamp"], 16)


async def get_logs_by_topic(from_block: int, to_block: int, topic0: str,
                            cli: httpx.AsyncClient) -> List[Dict]:
    return await rpc(
        "eth_getLogs",
        [{
            "address": KNOWN_LOCKERS,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "topics": [topic0],
        }],
        cli,
    )


async def get_tx_receipt(tx_hash: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    return await rpc("eth_getTransactionReceipt", [tx_hash], cli)


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


SEL_SYMBOL = "0x95d89b41"
SEL_NAME = "0x06fdde03"
SEL_DECIMALS = "0x313ce567"


async def fetch_token_meta_onchain(addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    try:
        sym_raw = await rpc("eth_call", [{"to": addr, "data": SEL_SYMBOL}, "latest"], cli)
        name_raw = await rpc("eth_call", [{"to": addr, "data": SEL_NAME}, "latest"], cli)
        dec_raw = await rpc("eth_call", [{"to": addr, "data": SEL_DECIMALS}, "latest"], cli)
        decimals = int(dec_raw, 16) if dec_raw and dec_raw != "0x" else 18
        return {
            "address": addr.lower(),
            "symbol": _hex_to_string(sym_raw) or "TOK",
            "name": _hex_to_string(name_raw) or "Unknown",
            "decimals": decimals,
        }
    except Exception as e:
        logger.debug(f"on-chain meta fail {addr}: {e}")
        return {"address": addr.lower(), "symbol": "TOK", "name": "Unknown", "decimals": 18}


# ============================================================
# BANKR LAUNCHES REGISTRY
# ============================================================
async def sync_bankr_launches(cli: httpx.AsyncClient, max_pages: int = 100):
    upserted = 0
    page = 0
    consecutive_failures = 0
    while page < max_pages:
        try:
            r = await cli.get(
                f"{BANKR_API}/token-launches",
                params={"limit": 50, "offset": page * 50},
                headers=BANKR_HEADERS,
                timeout=10.0,
            )
            if r.status_code == 429 or r.status_code == 503:
                consecutive_failures += 1
                if consecutive_failures > 6:
                    logger.warning(f"launches sync: 6+ rate-limit failures, stopping at page {page}")
                    break
                await asyncio.sleep(5.0 * consecutive_failures)
                continue
            if r.status_code != 200:
                consecutive_failures += 1
                if consecutive_failures > 3:
                    break
                await asyncio.sleep(2.0)
                continue
            consecutive_failures = 0
            launches = (r.json() or {}).get("launches", [])
            if not launches:
                break
            for L in launches:
                addr = (L.get("tokenAddress") or "").lower()
                if not addr:
                    continue
                for k in ("deployer", "feeRecipient"):
                    if isinstance(L.get(k), dict) and L[k].get("walletAddress"):
                        L[k]["walletAddress"] = L[k]["walletAddress"].lower()
                L["tokenAddress"] = addr
                await db.bankr_launches.update_one(
                    {"tokenAddress": addr}, {"$set": L}, upsert=True
                )
                upserted += 1
            if len(launches) < 50:
                break
            page += 1
            await asyncio.sleep(0.2)  # authenticated — go faster
        except Exception as e:
            logger.warning(f"launches sync page {page} failed: {e}")
            consecutive_failures += 1
            if consecutive_failures > 3:
                break
            await asyncio.sleep(2.0)
    if upserted:
        logger.info(f"bankr launches synced: {upserted} records (pages 0..{page})")
    return upserted


async def launches_syncer_loop():
    async with httpx.AsyncClient() as cli:
        await sync_bankr_launches(cli, max_pages=300)
        while True:
            await asyncio.sleep(180)
            try:
                await sync_bankr_launches(cli, max_pages=20)
            except Exception as e:
                logger.warning(f"launches sync error: {e}")


async def lookup_bankr_creator(token_addr: str) -> Dict[str, Any]:
    """Returns dict with handle, avatar, wallet, tweet_url if known."""
    doc = await db.bankr_launches.find_one(
        {"tokenAddress": token_addr.lower()}, {"_id": 0}
    )
    if not doc:
        return {}
    rec = doc.get("feeRecipient") or doc.get("deployer") or {}
    # if feeRecipient has no xUsername but deployer does, use deployer's
    if not rec.get("xUsername") and isinstance(doc.get("deployer"), dict):
        if doc["deployer"].get("xUsername"):
            rec = doc["deployer"]
    return {
        "handle": rec.get("xUsername"),
        "avatar": rec.get("xProfileImageUrl"),
        "wallet": rec.get("walletAddress"),
        "tweet_url": doc.get("tweetUrl"),
        "symbol_from_registry": doc.get("tokenSymbol"),
        "name_from_registry": doc.get("tokenName"),
    }


async def fetch_bankr_token_creator_live(token_addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    """Fallback for tokens not in our /token-launches sync (which only returns
    the latest 50). Uses authenticated /token-launches/{addr} which returns the
    full launch record including feeRecipient.xUsername."""
    try:
        r = await cli.get(
            f"{BANKR_API}/token-launches/{token_addr}",
            headers=BANKR_HEADERS, timeout=8.0,
        )
        if r.status_code != 200:
            return {}
        body = r.json() or {}
        launch = body.get("launch") or body
        if not isinstance(launch, dict):
            return {}
        # cache the full launch in bankr_launches for future lookups
        addr = (launch.get("tokenAddress") or token_addr).lower()
        for k in ("deployer", "feeRecipient"):
            if isinstance(launch.get(k), dict) and launch[k].get("walletAddress"):
                launch[k]["walletAddress"] = launch[k]["walletAddress"].lower()
        launch["tokenAddress"] = addr
        await db.bankr_launches.update_one(
            {"tokenAddress": addr}, {"$set": launch}, upsert=True
        )
        rec = launch.get("feeRecipient") or launch.get("deployer") or {}
        if not rec.get("xUsername") and isinstance(launch.get("deployer"), dict):
            if launch["deployer"].get("xUsername"):
                rec = launch["deployer"]
        handle = rec.get("xUsername")
        return {
            "handle": handle,
            "avatar": rec.get("xProfileImageUrl")
                      or (f"https://unavatar.io/x/{handle}" if handle else None),
            "wallet": rec.get("walletAddress"),
            "tweet_url": launch.get("tweetUrl"),
            "symbol_from_registry": launch.get("tokenSymbol"),
            "name_from_registry": launch.get("tokenName"),
        }
    except Exception as e:
        logger.debug(f"live bankr creator lookup fail {token_addr}: {e}")
    return {}


# ============================================================
# DEXSCREENER (market cap, liquidity, FDV)
# ============================================================
async def fetch_dexscreener(token_addr: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    try:
        r = await cli.get(f"{DEXSCREENER_API}/{token_addr}", timeout=8.0)
        if r.status_code != 200:
            return {}
        body = r.json() or {}
        pairs = body.get("pairs") or []
        if not pairs:
            return {}
        # pick the highest liquidity pair
        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
        top = pairs[0]
        liq = top.get("liquidity") or {}
        return {
            "market_cap_usd": float(top.get("marketCap") or 0),
            "fdv_usd": float(top.get("fdv") or 0),
            "liquidity_usd": float(liq.get("usd") or 0),
            "price_usd": float(top.get("priceUsd") or 0),
            "dex": top.get("dexId"),
            "pair_address": top.get("pairAddress"),
            "url": top.get("url"),
        }
    except Exception as e:
        logger.debug(f"dexscreener fail {token_addr}: {e}")
        return {}


# ============================================================
# TWITTERAPI.IO — X profile (followers count) lookup with caching
# ============================================================
async def fetch_x_profile(username: str, cli: httpx.AsyncClient) -> Dict[str, Any]:
    """Returns {followers, following, verified, bio, profilePicture} for an X handle.
    Caches in MongoDB to avoid hitting the API on every event."""
    if not username or not TWITTERAPI_IO_KEY:
        return {}
    username = username.strip().lstrip("@")
    # check cache
    cached = await db.x_profiles.find_one({"username_lower": username.lower()}, {"_id": 0})
    if cached:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(cached["fetched_at"])).total_seconds()
            if age < X_PROFILE_TTL_SECONDS:
                return cached
        except Exception:
            pass

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
            "username_lower": (data.get("userName") or username).lower(),
            "display_name": data.get("name"),
            "followers": int(data.get("followers") or 0),
            "following": int(data.get("following") or 0),
            "tweets": int(data.get("statusesCount") or 0),
            "is_verified": bool(data.get("isVerified") or data.get("isBlueVerified")),
            "is_blue": bool(data.get("isBlueVerified")),
            "bio": data.get("description"),
            "profile_picture": data.get("profilePicture"),
            "created_at": data.get("createdAt"),
            "fetched_at": now_iso(),
        }
        await db.x_profiles.update_one(
            {"username_lower": profile["username_lower"]},
            {"$set": profile},
            upsert=True,
        )
        return profile
    except Exception as e:
        logger.debug(f"x_profile fetch fail @{username}: {e}")
        return cached or {}


def _fmt_followers(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.1f}K"
    return f"{n}"


# ============================================================
# TELEGRAM ALERTING
# ============================================================
def _esc_html(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_compact_usd(v: float) -> str:
    v = float(v or 0)
    if v >= 1_000_000_000:
        return f"${v/1e9:.2f}B"
    if v >= 1_000_000:
        return f"${v/1e6:.2f}M"
    if v >= 1_000:
        return f"${v/1e3:.2f}K"
    return f"${v:,.2f}"


def _fmt_amount(v: float, max_dec: int = 4) -> str:
    v = float(v or 0)
    return f"{v:,.{max_dec}f}"


def build_telegram_message(event: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Telegram message + inline keyboard for a claim event."""
    token_addr = event.get("token_address") or ""
    handle = event.get("claimer_handle")
    benef = event.get("beneficiary") or event.get("claimer_wallet") or ""

    if handle:
        benef_line = f"@{_esc_html(handle)}\n  <code>{_esc_html(benef)}</code>"
    else:
        benef_line = f"<code>{_esc_html(benef)}</code>"

    symbol = _esc_html(event.get("token_symbol") or "?")
    name = _esc_html(event.get("token_name") or "?")
    tok_amount = _fmt_amount(event.get("released_token_amount") or 0)
    weth_amount = _fmt_amount(event.get("released_weth_amount") or 0, max_dec=6)
    usd_amount = _fmt_compact_usd(event.get("released_usd") or 0)
    mc = _fmt_compact_usd(event.get("market_cap_usd") or 0)
    liq = _fmt_compact_usd(event.get("liquidity_usd") or 0)

    text = (
        "🎉 <b>NEW BANKR FEE CLAIMED!</b>\n\n"
        "<b>Token Information:</b>\n"
        f"• Name: <b>{name}</b>\n"
        f"• Symbol: <b>${symbol}</b>\n"
        f"• Contract: <code>{_esc_html(token_addr)}</code>\n"
        f"• Market Cap: <b>{mc}</b>\n"
        f"• Liquidity: <b>{liq}</b>\n\n"
        "<b>Released to Beneficiary:</b>\n"
        f"• Token Amount: <b>{tok_amount} ${symbol}</b>\n"
        f"• ETH Amount: <b>{weth_amount} ETH</b> ({usd_amount})\n"
        f"• Beneficiary: {benef_line}"
    )

    # Inline keyboard
    keyboard: List[List[Dict[str, str]]] = []
    if token_addr:
        keyboard.append([
            {"text": "🚀 Bankr Launch", "url": f"https://bankr.bot/launches/{token_addr}"},
        ])
        keyboard.append([
            {"text": "💰 Buy", "url": f"https://t.me/based_rescue_bot?start=r_botprivacy_b_{token_addr}"},
        ])
        keyboard.append([
            {"text": "📈 GMGN", "url": f"https://gmgn.ai/base/token/{token_addr}"},
        ])
        keyboard.append([
            {"text": "🔍 Search on X", "url": f"https://twitter.com/search?q={token_addr}"},
        ])
    if handle:
        keyboard.append([
            {"text": f"𝕏 Beneficiary @{handle}",
             "url": f"https://twitter.com/{handle}"},
        ])

    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}


async def send_telegram_alert(event: Dict[str, Any], cli: httpx.AsyncClient) -> bool:
    if not TELEGRAM_ENABLED or not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        return False
    try:
        msg = build_telegram_message(event)
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
        logger.warning(f"telegram alert failed: {r.status_code} {r.text[:200]}")
    except Exception as e:
        logger.warning(f"telegram alert exception: {e}")
    return False


# ============================================================
# CORE — process Released events
# ============================================================
async def rpc_unfiltered(method: str, params: list, cli: httpx.AsyncClient,
                          retries: int = 3) -> Any:
    """Like rpc() but pinned to mainnet.base.org which allows queries without
    address filter. Used only for the limited Transfer log queries."""
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
        except (httpx.HTTPError, httpx.ConnectError, asyncio.TimeoutError) as e:
            last_err = e
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
    raise RuntimeError(f"unfiltered RPC failed: {last_err}")


async def get_outbound_transfers(from_block: int, to_block: int,
                                  cli: httpx.AsyncClient) -> List[Dict]:
    """Fetch all ERC20 Transfer events with from = known locker contracts.
    Uses unfiltered RPC because we don't know which token contract emitted."""
    out = []
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


def _build_transfer_index(transfers: List[Dict]) -> Dict[str, List[Dict]]:
    """Index Transfer logs by (tx_hash) for fast lookup."""
    idx: Dict[str, List[Dict]] = {}
    for log in transfers:
        idx.setdefault(log["transactionHash"], []).append(log)
    return idx


def find_token_from_transfers(tx_transfers: List[Dict], locker: str,
                               beneficiary: str) -> Optional[Dict[str, Any]]:
    """Within a single tx's Transfer logs, find the launched token (non-WETH transfer
    from locker to beneficiary)."""
    locker_l = locker.lower()
    benef_l = beneficiary.lower()
    for log in tx_transfers:
        frm = "0x" + log["topics"][1][-40:].lower()
        to = "0x" + log["topics"][2][-40:].lower()
        tok = log["address"].lower()
        if frm == locker_l and to == benef_l and tok != WETH_BASE.lower():
            return {"token_address": tok, "log": log}
    return None


async def process_released_event(
    log: Dict[str, Any],
    tx_transfers: List[Dict[str, Any]],
    block_ts_cache: Dict[str, int],
    cli: httpx.AsyncClient,
    live_alerts: bool = False,
) -> bool:
    """Returns True if a new claim event was inserted."""
    try:
        tx_hash = log["transactionHash"]
        log_index = int(log["logIndex"], 16)
        block_number = int(log["blockNumber"], 16)
        locker = log["address"].lower()
        pool_id = log["topics"][1]
        beneficiary = "0x" + log["topics"][2][-40:].lower()
        data = log["data"].replace("0x", "")
        amt0_raw = int(data[0:64], 16) if len(data) >= 64 else 0
        amt1_raw = int(data[64:128], 16) if len(data) >= 128 else 0

        if amt0_raw == 0 and amt1_raw == 0:
            return False

        key = f"{tx_hash}-{log_index}"
        if await db.claim_events.find_one({"key": key}, {"_id": 1}):
            return False

        # Find token via pre-fetched Transfer logs
        token_info = find_token_from_transfers(tx_transfers, locker, beneficiary)
        token_addr = token_info["token_address"] if token_info else None

        # Determine which amount is WETH and which is the token.
        # Bankr convention: token0 = the address with LOWER hex value (per Uniswap V4)
        # WETH on Base = 0x4200000000000000000000000000000000000006
        token_amount_raw = amt0_raw
        weth_amount_raw = amt1_raw
        if token_addr:
            if int(token_addr, 16) > int(WETH_BASE, 16):
                token_amount_raw, weth_amount_raw = amt1_raw, amt0_raw
        else:
            # token_address couldn't be resolved from inner Transfer logs.
            # Use a magnitude-based heuristic — WETH amounts realistically cap at
            # ~1000 ETH = 10^21 wei. Anything larger MUST be the launched token.
            WETH_CAP_RAW = 10 ** 21
            if amt0_raw > WETH_CAP_RAW and amt1_raw <= WETH_CAP_RAW:
                token_amount_raw, weth_amount_raw = amt0_raw, amt1_raw
            elif amt1_raw > WETH_CAP_RAW and amt0_raw <= WETH_CAP_RAW:
                token_amount_raw, weth_amount_raw = amt1_raw, amt0_raw
            elif amt0_raw == 0:
                # only one leg has value — assume WETH if it's reasonable, else token
                if amt1_raw <= WETH_CAP_RAW:
                    weth_amount_raw, token_amount_raw = amt1_raw, 0
                else:
                    weth_amount_raw, token_amount_raw = 0, amt1_raw
            elif amt1_raw == 0:
                if amt0_raw <= WETH_CAP_RAW:
                    weth_amount_raw, token_amount_raw = amt0_raw, 0
                else:
                    weth_amount_raw, token_amount_raw = 0, amt0_raw
            else:
                # both moderate — assume token0=token, token1=WETH
                token_amount_raw, weth_amount_raw = amt0_raw, amt1_raw

        weth_amount = weth_amount_raw / 1e18

        # Token meta — registry first, then on-chain
        token_symbol = "?"
        token_name = "?"
        token_decimals = 18
        if token_addr:
            tok_doc = await db.tokens.find_one({"address": token_addr}, {"_id": 0})
            if tok_doc and tok_doc.get("symbol") and tok_doc["symbol"] not in ("TOK", "?"):
                token_symbol = tok_doc["symbol"]
                token_name = tok_doc.get("name", "")
                token_decimals = int(tok_doc.get("decimals", 18))
            else:
                bcr = await lookup_bankr_creator(token_addr)
                if bcr.get("symbol_from_registry"):
                    token_symbol = bcr["symbol_from_registry"]
                    token_name = bcr.get("name_from_registry", "")
                else:
                    meta = await fetch_token_meta_onchain(token_addr, cli)
                    token_symbol = meta["symbol"]
                    token_name = meta["name"]
                    token_decimals = meta["decimals"]

        token_amount = token_amount_raw / (10 ** token_decimals) if token_addr else 0

        creator = await lookup_bankr_creator(token_addr) if token_addr else {}
        # Live fallback — when the token isn't in our local cache yet
        # (just launched / between sync cycles), hit Bankr's API directly.
        if token_addr and not creator.get("handle"):
            live = await fetch_bankr_token_creator_live(token_addr, cli)
            if live.get("handle"):
                creator = live
        claimer_handle = creator.get("handle")
        claimer_avatar = creator.get("avatar")
        if not claimer_avatar and claimer_handle:
            claimer_avatar = f"https://unavatar.io/x/{claimer_handle}"

        # X profile lookup (followers / verified) is intentionally skipped here
        # so Telegram alerts go out as fast as possible. The dashboard can fetch
        # it lazily for the claimer-detail page.
        x_profile: Dict[str, Any] = {}

        # Block timestamp from cache
        ts = block_ts_cache.get(log["blockNumber"])
        if ts is None:
            try:
                ts = await get_block_timestamp(log["blockNumber"], cli)
                block_ts_cache[log["blockNumber"]] = ts
            except Exception:
                ts = int(datetime.now(timezone.utc).timestamp())
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # DexScreener market data (skip if already cached for this token in the last hour)
        market_cap_usd = 0
        liquidity_usd = 0
        price_usd = 0
        if token_addr:
            cached = await db.tokens.find_one(
                {"address": token_addr}, {"market_cap_usd": 1, "liquidity_usd": 1, "price_usd": 1, "last_polled": 1}
            )
            fresh_enough = False
            if cached and cached.get("last_polled"):
                try:
                    age = (datetime.now(timezone.utc) -
                           datetime.fromisoformat(cached["last_polled"])).total_seconds()
                    fresh_enough = age < 3600
                except Exception:
                    pass
            if fresh_enough and cached:
                market_cap_usd = cached.get("market_cap_usd") or 0
                liquidity_usd = cached.get("liquidity_usd") or 0
                price_usd = cached.get("price_usd") or 0
            else:
                ds = await fetch_dexscreener(token_addr, cli)
                market_cap_usd = ds.get("market_cap_usd") or ds.get("fdv_usd") or 0
                liquidity_usd = ds.get("liquidity_usd", 0)
                price_usd = ds.get("price_usd", 0)

        amount_usd = round(weth_amount * ETH_PRICE_USD, 2)

        event = {
            "id": str(uuid.uuid4()),
            "key": key,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "log_index": log_index,
            "locker_contract": locker,
            "pool_id": pool_id,
            "token_address": token_addr,
            "token_symbol": token_symbol,
            "token_name": token_name,
            "token_decimals": token_decimals,
            "beneficiary": beneficiary,
            "claimer_wallet": beneficiary,
            "claimer_handle": claimer_handle,
            "claimer_avatar": claimer_avatar
                or (f"https://unavatar.io/x/{claimer_handle}" if claimer_handle
                    else f"https://api.dicebear.com/9.x/identicon/svg?seed={beneficiary}&backgroundColor=00FF66"),
            "claimer_followers": int(x_profile.get("followers") or 0),
            "claimer_following": int(x_profile.get("following") or 0),
            "claimer_verified": bool(x_profile.get("is_verified") or x_profile.get("is_blue")),
            "claimer_bio": x_profile.get("bio"),
            "released_token_amount": token_amount,
            "released_weth_amount": weth_amount,
            "released_usd": amount_usd,
            "amount_eth": weth_amount,
            "amount_token": token_amount,
            "amount_usd": amount_usd,
            "market_cap_usd": market_cap_usd,
            "liquidity_usd": liquidity_usd,
            "price_usd": price_usd,
            "chain": "base",
            "source": "onchain_released",
            "tweet_url": creator.get("tweet_url"),
            "timestamp": timestamp,
        }
        await db.claim_events.insert_one(event)

        if token_addr:
            await db.tokens.update_one(
                {"address": token_addr},
                {
                    "$set": {
                        "address": token_addr,
                        "symbol": token_symbol,
                        "name": token_name,
                        "decimals": token_decimals,
                        "chain": "base",
                        "creator_handle": claimer_handle,
                        "creator_avatar": event["claimer_avatar"],
                        "creator_wallet": creator.get("wallet"),
                        "tweet_url": creator.get("tweet_url"),
                        "market_cap_usd": market_cap_usd,
                        "liquidity_usd": liquidity_usd,
                        "price_usd": price_usd,
                        "last_polled": now_iso(),
                        "last_claim": timestamp,
                    },
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "first_seen": now_iso(),
                    },
                    "$inc": {
                        "total_claimed_eth": weth_amount,
                        "total_claimed_usd": amount_usd,
                        "total_claimed_token": token_amount,
                        "total_claim_count": 1,
                    },
                },
                upsert=True,
            )

        logger.info(
            f"NEW CLAIM: @{claimer_handle or '???'} got "
            f"{token_amount:.4f} ${token_symbol} + {weth_amount:.6f} ETH "
            f"(MC ${market_cap_usd:,.0f}) tx={tx_hash[:12]}"
        )

        # Telegram alert — ONLY for live events (near tip), never for backfill
        tg_sent = False
        if live_alerts and weth_amount > 0:
            tg_sent = await send_telegram_alert(event, cli)

        return {"new": True, "tg_sent": tg_sent}
    except Exception as e:
        logger.error(f"process_released_event err: {e}")
        return False


async def onchain_indexer_loop():
    logger.info("On-chain Released event indexer started")
    async with httpx.AsyncClient() as cli:
        state = await db.indexer_state.find_one({"_id": "main"})
        if state and state.get("last_block"):
            last_block = int(state["last_block"])
        else:
            tip = await get_block_number(cli)
            last_block = max(0, tip - INITIAL_BACKFILL_BLOCKS)
            logger.info(f"first run: backfilling from block {last_block}")

        while True:
            try:
                tip = await get_block_number(cli)
                if last_block >= tip:
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue
                from_block = last_block + 1
                to_block = min(tip, from_block + BLOCKS_PER_QUERY - 1)

                # Fetch Released events AND outbound Transfer events in parallel
                released_logs = await get_logs_by_topic(from_block, to_block, RELEASED_TOPIC, cli)
                transfer_logs = await get_outbound_transfers(from_block, to_block, cli)
                tx_idx = _build_transfer_index(transfer_logs)

                # Only alert on Telegram once we're caught up close to chain tip
                # (avoids spamming the channel during initial backfill)
                live_alerts = (tip - to_block) <= TELEGRAM_LIVE_BLOCK_THRESHOLD

                block_ts_cache: Dict[str, int] = {}
                new_count = 0
                alerts_sent = 0
                for log in released_logs:
                    transfers_for_tx = tx_idx.get(log["transactionHash"], [])
                    res = await process_released_event(
                        log, transfers_for_tx, block_ts_cache, cli, live_alerts=live_alerts
                    )
                    if isinstance(res, dict) and res.get("new"):
                        new_count += 1
                        if res.get("tg_sent"):
                            alerts_sent += 1

                if released_logs:
                    suffix = f" · {alerts_sent} TG alerts" if live_alerts and alerts_sent else ""
                    logger.info(
                        f"blocks {from_block}-{to_block}: {len(released_logs)} released "
                        f"({len(transfer_logs)} transfers), {new_count} new claims{suffix}"
                    )
                last_block = to_block
                await db.indexer_state.update_one(
                    {"_id": "main"},
                    {"$set": {"last_block": last_block, "updated_at": now_iso(), "version": 4}},
                    upsert=True,
                )
                if last_block >= tip - 5:
                    await asyncio.sleep(POLL_INTERVAL_S)
                else:
                    await asyncio.sleep(0.5)
            except Exception as e:
                msg = str(e).lower()
                if "rate" in msg or "limit" in msg:
                    logger.warning(f"RPC rate-limit, backing off: {e}")
                    await asyncio.sleep(15)
                else:
                    logger.error(f"indexer loop err: {e}")
                    await asyncio.sleep(POLL_INTERVAL_S)


async def price_refresher_loop():
    while True:
        await asyncio.sleep(300)
        await fetch_eth_price()


async def token_resolver_loop():
    """Background task: re-resolve tokens that still show '?' or missing
    creator handle. Iterates through all tracked tokens periodically and
    queries the Bankr live token-fees endpoint."""
    await asyncio.sleep(15)
    async with httpx.AsyncClient() as cli:
        while True:
            try:
                cur = db.tokens.find(
                    {"$or": [
                        {"symbol": {"$in": ["?", "TOK", "Unknown", None]}},
                        {"creator_handle": {"$in": [None, ""]}},
                    ]},
                    {"_id": 0, "address": 1, "symbol": 1, "creator_handle": 1},
                ).limit(100)
                tokens_to_fix = await cur.to_list(100)
                if not tokens_to_fix:
                    await asyncio.sleep(60)
                    continue
                fixed = 0
                for t in tokens_to_fix:
                    addr = t["address"]
                    new_sym = None
                    new_name = None
                    handle = None
                    avatar = None
                    bcr = await lookup_bankr_creator(addr)
                    if bcr.get("symbol_from_registry"):
                        new_sym = bcr["symbol_from_registry"]
                        new_name = bcr.get("name_from_registry")
                        handle = bcr.get("handle")
                        avatar = bcr.get("avatar")
                    if not handle:
                        live = await fetch_bankr_token_creator_live(addr, cli)
                        if not new_sym and live.get("symbol_from_registry"):
                            new_sym = live["symbol_from_registry"]
                            new_name = live.get("name_from_registry")
                        if live.get("handle"):
                            handle = live["handle"]
                            avatar = live.get("avatar")
                    if not new_sym and (not t.get("symbol") or t.get("symbol") in ("TOK", "?", "Unknown")):
                        meta = await fetch_token_meta_onchain(addr, cli)
                        if meta["symbol"] not in ("TOK", "?", "Unknown"):
                            new_sym = meta["symbol"]
                            new_name = meta["name"]
                    if new_sym or handle:
                        token_set: Dict[str, Any] = {}
                        if new_sym:
                            token_set["symbol"] = new_sym
                            token_set["name"] = new_name or "Unknown"
                        if handle:
                            token_set["creator_handle"] = handle
                            token_set["creator_avatar"] = avatar or f"https://unavatar.io/x/{handle}"
                        await db.tokens.update_one({"address": addr}, {"$set": token_set})
                        evt_set: Dict[str, Any] = {}
                        if new_sym:
                            evt_set["token_symbol"] = new_sym
                            evt_set["token_name"] = new_name or "Unknown"
                        if handle:
                            evt_set["claimer_handle"] = handle
                            evt_set["claimer_avatar"] = avatar or f"https://unavatar.io/x/{handle}"
                        if evt_set:
                            await db.claim_events.update_many(
                                {"token_address": addr}, {"$set": evt_set}
                            )
                        fixed += 1
                    await asyncio.sleep(0.4)  # authenticated — faster
                if fixed:
                    logger.info(f"token_resolver: fixed {fixed} of {len(tokens_to_fix)} tokens")
            except Exception as e:
                logger.warning(f"token_resolver error: {e}")
            await asyncio.sleep(10)


# ============================================================
# API ROUTES
# ============================================================
@api_router.post("/telegram/test")
async def telegram_test():
    """Send a sample claim card to the Telegram channel to verify wiring."""
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        raise HTTPException(status_code=400, detail="Telegram not configured")
    sample = await db.claim_events.find_one(
        {"claimer_handle": {"$ne": None}, "released_weth_amount": {"$gt": 0}},
        {"_id": 0}, sort=[("timestamp", -1)],
    )
    if not sample:
        raise HTTPException(status_code=404, detail="no claim events to send yet")
    # Enrich with fresh X profile for the demo card
    async with httpx.AsyncClient() as cli:
        if sample.get("claimer_handle"):
            prof = await fetch_x_profile(sample["claimer_handle"], cli)
            if prof:
                sample["claimer_followers"] = int(prof.get("followers") or 0)
                sample["claimer_following"] = int(prof.get("following") or 0)
                sample["claimer_verified"] = bool(prof.get("is_verified") or prof.get("is_blue"))
                sample["claimer_bio"] = prof.get("bio")
                # propagate to all events for this handle
                await db.claim_events.update_many(
                    {"claimer_handle": sample["claimer_handle"]},
                    {"$set": {
                        "claimer_followers": sample["claimer_followers"],
                        "claimer_verified": sample["claimer_verified"],
                    }},
                )
        ok = await send_telegram_alert(sample, cli)
    return {
        "sent": ok,
        "sample_id": sample["id"],
        "token": sample.get("token_symbol"),
        "handle": sample.get("claimer_handle"),
        "followers": sample.get("claimer_followers"),
    }


@api_router.get("/")
async def root():
    state = await db.indexer_state.find_one({"_id": "main"})
    return {
        "service": "bankr-bot-claim-monitor",
        "version": "4.0.0",
        "chain": "base",
        "event_topic": RELEASED_TOPIC,
        "indexer_last_block": (state or {}).get("last_block"),
        "data_source": "on-chain Released events + bankr public API + dexscreener",
    }


@api_router.get("/health")
async def health():
    """Lightweight keep-alive endpoint. Ping every 1-5 min via UptimeRobot
    or similar to prevent the deployed container from going idle and
    pausing the background indexer that pushes Telegram alerts."""
    return {"ok": True, "ts": now_iso()}


@api_router.get("/stats")
async def stats():
    total_events = await db.claim_events.count_documents({})
    agg = await db.claim_events.aggregate([
        {"$group": {"_id": None,
                    "total_eth": {"$sum": "$amount_eth"},
                    "total_usd": {"$sum": "$amount_usd"}}}
    ]).to_list(1)
    total_eth = float(agg[0]["total_eth"]) if agg else 0.0
    total_usd = float(agg[0]["total_usd"]) if agg else 0.0

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    last_24h = await db.claim_events.count_documents({"timestamp": {"$gte": since}})
    agg24 = await db.claim_events.aggregate([
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": None,
                    "eth": {"$sum": "$amount_eth"},
                    "usd": {"$sum": "$amount_usd"}}}
    ]).to_list(1)
    eth_24h = float(agg24[0]["eth"]) if agg24 else 0.0
    usd_24h = float(agg24[0]["usd"]) if agg24 else 0.0

    unique_wallets = len(
        await db.claim_events.distinct("beneficiary", {"beneficiary": {"$ne": ""}})
    )
    unique_handles = len(
        await db.claim_events.distinct("claimer_handle", {"claimer_handle": {"$ne": None}})
    )
    bankr_launches = await db.bankr_launches.count_documents({})
    tracked_tokens = await db.tokens.count_documents({})
    state = await db.indexer_state.find_one({"_id": "main"})

    return {
        "total_claims": total_events,
        "total_eth": round(total_eth, 6),
        "total_usd": round(total_usd, 2),
        "claims_24h": last_24h,
        "eth_24h": round(eth_24h, 6),
        "usd_24h": round(usd_24h, 2),
        "unique_claimers": unique_wallets,
        "unique_handles": unique_handles,
        "lifetime_eth": round(total_eth, 4),
        "lifetime_usd": round(total_usd, 2),
        "lifetime_claim_count": total_events,
        "bankr_launches_indexed": bankr_launches,
        "tracked_tokens": tracked_tokens,
        "eth_price_usd": round(ETH_PRICE_USD, 2),
        "indexer_last_block": (state or {}).get("last_block"),
        "event_topic": RELEASED_TOPIC,
    }


@api_router.get("/claims/feed")
async def claims_feed(
    limit: int = Query(40, ge=1, le=200),
    skip: int = Query(0, ge=0),
    handle: Optional[str] = None,
    token: Optional[str] = None,
):
    query: Dict[str, Any] = {}
    if handle:
        query["claimer_handle"] = {"$regex": f"^{handle}", "$options": "i"}
    if token:
        query["$or"] = [
            {"token_symbol": {"$regex": token, "$options": "i"}},
            {"token_address": token.lower()},
        ]
    cur = (
        db.claim_events.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    items = await cur.to_list(limit)
    return {"items": items, "count": len(items)}


@api_router.get("/claims/{event_id}/card")
async def claim_card(event_id: str):
    """Returns the formatted claim card text — Telegram/Discord-friendly."""
    e = await db.claim_events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="event not found")
    handle = e.get("claimer_handle")
    handle_line = f"@{handle} ({e['beneficiary'][:6]}…{e['beneficiary'][-4:]})" if handle else e["beneficiary"]
    lines = [
        "🎉 NEW BANKR FEE CLAIMED!",
        "",
        "Token Information:",
        f"• Name: {e.get('token_name','?')}",
        f"• Symbol: ${e.get('token_symbol','?')}",
        f"• Contract: {e.get('token_address')}",
        f"• Market Cap: ${e.get('market_cap_usd',0):,.2f}",
        f"• Liquidity: ${e.get('liquidity_usd',0):,.2f}",
        "",
        "Released to Beneficiary:",
        f"• Token Amount: {e.get('released_token_amount',0):.4f} {e.get('token_symbol','')}",
        f"• ETH Amount: {e.get('released_weth_amount',0):.6f} ETH (${e.get('released_usd',0):,.2f})",
        f"• Beneficiary: {handle_line}",
        "",
        f"Tx: https://basescan.org/tx/{e['tx_hash']}",
    ]
    return {"card": "\n".join(lines), "event": e}


@api_router.get("/leaderboard")
async def leaderboard(limit: int = Query(15, ge=1, le=100)):
    pipeline = [
        {"$group": {
            "_id": {"handle": "$claimer_handle", "wallet": "$beneficiary"},
            "total_eth": {"$sum": "$amount_eth"},
            "total_usd": {"$sum": "$amount_usd"},
            "claim_count": {"$sum": 1},
            "avatar": {"$first": "$claimer_avatar"},
            "last_claim": {"$max": "$timestamp"},
        }},
        {"$sort": {"total_eth": -1}},
        {"$limit": limit},
    ]
    rows = await db.claim_events.aggregate(pipeline).to_list(limit)
    out = []
    for i, r in enumerate(rows):
        out.append({
            "rank": i + 1,
            "handle": r["_id"].get("handle"),
            "wallet": r["_id"].get("wallet"),
            "avatar": r.get("avatar"),
            "total_eth": round(float(r["total_eth"]), 6),
            "total_usd": round(float(r["total_usd"]), 2),
            "claim_count": int(r["claim_count"]),
            "last_claim": r.get("last_claim"),
        })
    return {"items": out}


@api_router.get("/leaderboard/lifetime")
async def leaderboard_lifetime(limit: int = Query(15, ge=1, le=100)):
    """Top fee claimers ranked by total ETH claimed across all events.
    Shows X handle when resolved, wallet otherwise."""
    pipeline = [
        {"$group": {
            "_id": {
                "handle": "$claimer_handle",
                "wallet": "$beneficiary",
            },
            "lifetime_eth": {"$sum": "$amount_eth"},
            "claim_count": {"$sum": 1},
            "tokens": {"$addToSet": "$token_address"},
            "avatar": {"$first": "$claimer_avatar"},
        }},
        {"$sort": {"lifetime_eth": -1}},
        {"$limit": limit},
    ]
    rows = await db.claim_events.aggregate(pipeline).to_list(limit)
    out = []
    for i, r in enumerate(rows):
        eth = float(r.get("lifetime_eth") or 0)
        out.append({
            "rank": i + 1,
            "handle": r["_id"].get("handle"),
            "wallet": r["_id"].get("wallet"),
            "avatar": r.get("avatar"),
            "lifetime_eth": round(eth, 6),
            "lifetime_usd": round(eth * ETH_PRICE_USD, 2),
            "claim_count": int(r["claim_count"]),
            "tokens": len([t for t in (r.get("tokens") or []) if t]),
        })
    return {"items": out}


@api_router.get("/tokens")
async def list_tokens(limit: int = Query(100, ge=1, le=500)):
    cur = (
        db.tokens.find({}, {"_id": 0})
        .sort("total_claimed_eth", -1)
        .limit(limit)
    )
    items = await cur.to_list(limit)
    return {"items": items}


@api_router.get("/tokens/{address}")
async def token_detail(address: str):
    addr = address.lower()
    tok = await db.tokens.find_one({"address": addr}, {"_id": 0})
    if not tok:
        raise HTTPException(status_code=404, detail="token not found")
    since = datetime.now(timezone.utc) - timedelta(days=14)
    pipeline = [
        {"$match": {"token_address": addr, "timestamp": {"$gte": since.isoformat()}}},
        {"$group": {
            "_id": {"$substr": ["$timestamp", 0, 10]},
            "eth": {"$sum": "$amount_eth"},
            "usd": {"$sum": "$amount_usd"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    timeline = await db.claim_events.aggregate(pipeline).to_list(50)
    timeline_data = [
        {"date": t["_id"], "eth": round(float(t["eth"]), 6),
         "usd": round(float(t["usd"]), 2), "count": int(t["count"])}
        for t in timeline
    ]
    recent = (
        await db.claim_events.find({"token_address": addr}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(20)
        .to_list(20)
    )
    return {"token": tok, "timeline": timeline_data, "recent_claims": recent}


@api_router.get("/handle/{handle}")
async def claimer_detail(handle: str):
    events = (
        await db.claim_events.find({"claimer_handle": handle}, {"_id": 0})
        .sort("timestamp", -1).limit(100).to_list(100)
    )
    if not events:
        raise HTTPException(status_code=404, detail="no claims found for handle")
    total_eth = sum(e["amount_eth"] for e in events)
    total_usd = sum(e["amount_usd"] for e in events)
    tokens_claimed = sorted({e["token_symbol"] for e in events if e.get("token_symbol")})
    return {
        "handle": handle,
        "avatar": events[0].get("claimer_avatar"),
        "wallet": events[0].get("beneficiary"),
        "x_url": f"https://x.com/{handle}",
        "total_eth": round(total_eth, 6),
        "total_usd": round(total_usd, 2),
        "lifetime_eth": round(total_eth, 6),
        "lifetime_eth_claimed": round(total_eth, 6),
        "claim_count": len(events),
        "tokens_owned": len(tokens_claimed),
        "tokens_claimed": tokens_claimed,
        "tokens": [],
        "claims": events,
    }


@api_router.get("/wallet/{address}")
async def wallet_detail(address: str):
    addr = address.lower()
    events = (
        await db.claim_events.find({"beneficiary": addr}, {"_id": 0})
        .sort("timestamp", -1).limit(100).to_list(100)
    )
    if not events:
        raise HTTPException(status_code=404, detail="no claims for wallet")
    total_eth = sum(e["amount_eth"] for e in events)
    total_usd = sum(e["amount_usd"] for e in events)
    handles = sorted({e["claimer_handle"] for e in events if e.get("claimer_handle")})
    return {
        "wallet": addr,
        "handle": handles[0] if handles else None,
        "all_handles": handles,
        "avatar": events[0].get("claimer_avatar"),
        "total_eth": round(total_eth, 6),
        "total_usd": round(total_usd, 2),
        "claim_count": len(events),
        "tokens_claimed": sorted({e["token_symbol"] for e in events if e.get("token_symbol")}),
        "claims": events,
    }


@api_router.get("/search")
async def search(q: str = Query(..., min_length=1)):
    qrx = {"$regex": q, "$options": "i"}
    handles = await db.claim_events.aggregate([
        {"$match": {"claimer_handle": qrx}},
        {"$group": {"_id": "$claimer_handle",
                    "avatar": {"$first": "$claimer_avatar"},
                    "total_eth": {"$sum": "$amount_eth"},
                    "count": {"$sum": 1}}},
        {"$limit": 10},
    ]).to_list(10)
    tokens = await db.tokens.find(
        {"$or": [{"symbol": qrx}, {"name": qrx}, {"address": q.lower()}]},
        {"_id": 0},
    ).limit(10).to_list(10)
    return {
        "handles": [
            {"handle": h["_id"], "avatar": h.get("avatar"),
             "total_eth": round(float(h.get("total_eth") or 0), 4),
             "count": int(h.get("count") or 0)} for h in handles
        ],
        "tokens": tokens,
    }


# ============================================================
# WIRE UP
# ============================================================
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_bg_tasks: List[asyncio.Task] = []


@app.on_event("startup")
async def startup_event():
    state = await db.indexer_state.find_one({"_id": "main"})
    if not state or (state and state.get("version", 0) < 4):
        # v3 -> v4: switch to Released-event indexing; reset claim events
        d1 = await db.claim_events.delete_many({})
        d2 = await db.tokens.delete_many({})
        await db.indexer_state.delete_many({})
        logger.info(
            f"v3->v4 migration: cleared {d1.deleted_count} events, {d2.deleted_count} tokens"
        )

    await db.claim_events.create_index([("timestamp", -1)])
    await db.claim_events.create_index([("token_address", 1)])
    await db.claim_events.create_index([("claimer_handle", 1)])
    await db.claim_events.create_index([("beneficiary", 1)])
    await db.claim_events.create_index([("key", 1)], unique=True)
    await db.tokens.create_index([("address", 1)], unique=True)
    await db.tokens.create_index([("creator_handle", 1)])
    await db.bankr_launches.create_index([("tokenAddress", 1)], unique=True)
    await db.bankr_launches.create_index([("feeRecipient.walletAddress", 1)])
    await db.x_profiles.create_index([("username_lower", 1)], unique=True)

    await fetch_eth_price()
    _bg_tasks.append(asyncio.create_task(launches_syncer_loop()))
    _bg_tasks.append(asyncio.create_task(price_refresher_loop()))
    _bg_tasks.append(asyncio.create_task(onchain_indexer_loop()))
    _bg_tasks.append(asyncio.create_task(token_resolver_loop()))
    logger.info("Bankr Monitor v4 startup complete · Released-event indexing")


@app.on_event("shutdown")
async def shutdown():
    for t in _bg_tasks:
        t.cancel()
    client.close()
