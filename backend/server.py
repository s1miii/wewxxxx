from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import random
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bankr-monitor")

# Create the main app without a prefix
app = FastAPI(title="Bankr Bot Claim Fee Monitor")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ============================================================
# MODELS
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Token(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    address: str
    symbol: str
    name: str
    creator_handle: str  # Twitter / X username
    creator_avatar: Optional[str] = None
    chain: str = "base"
    launched_at: str = Field(default_factory=now_iso)
    total_claimed_eth: float = 0.0
    total_claimed_usd: float = 0.0
    claimable_eth: float = 0.0
    last_polled: Optional[str] = None


class TokenCreate(BaseModel):
    address: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    creator_handle: Optional[str] = None


class ClaimEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    token_address: str
    token_symbol: str
    token_name: str
    claimer_handle: str  # twitter username
    claimer_avatar: Optional[str] = None
    claimer_wallet: str
    amount_eth: float
    amount_usd: float
    tx_hash: str
    block_number: int
    chain: str = "base"
    timestamp: str = Field(default_factory=now_iso)


# ============================================================
# SEED DATA (Realistic Bankr/Base ecosystem)
# ============================================================

# Known Bankr-style creators on X with realistic avatars
SEED_CREATORS = [
    {"handle": "aixbt_agent", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=aixbt_agent&backgroundColor=00FF66"},
    {"handle": "clankeronbase", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=clankeronbase&backgroundColor=00F0FF"},
    {"handle": "bnkrcrypto", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=bnkrcrypto&backgroundColor=FFE600"},
    {"handle": "0xMert_", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=0xMert&backgroundColor=FF007A"},
    {"handle": "basedmemes", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=basedmemes&backgroundColor=00FF66"},
    {"handle": "jessepollak", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=jessepollak&backgroundColor=0052FF"},
    {"handle": "wassielawyer", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=wassielawyer&backgroundColor=00F0FF"},
    {"handle": "tokenterminal", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=tokenterminal&backgroundColor=FFE600"},
    {"handle": "degenspartan", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=degenspartan&backgroundColor=FF007A"},
    {"handle": "saylor_ai", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=saylor_ai&backgroundColor=00FF66"},
    {"handle": "fartcoin_agent", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=fartcoin&backgroundColor=FFE600"},
    {"handle": "vitalik_bot", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=vitalik_bot&backgroundColor=00F0FF"},
    {"handle": "punk6529ai", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=punk6529ai&backgroundColor=FF007A"},
    {"handle": "luca_netz", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=luca_netz&backgroundColor=00FF66"},
    {"handle": "cobie_ai", "avatar": "https://api.dicebear.com/9.x/identicon/svg?seed=cobie_ai&backgroundColor=00F0FF"},
]

SEED_TOKENS = [
    {"address": "0x22aF33FE49fD1Fa80c7149773dDe5890D3c76F3b", "symbol": "BNKR", "name": "Bankr",
     "creator_handle": "bnkrcrypto"},
    {"address": "0x4f9Fd6Be4a90f2620860d680c0d4d5Fb53d1A825", "symbol": "AIXBT", "name": "aixbt by Virtuals",
     "creator_handle": "aixbt_agent"},
    {"address": "0x1bc0c42215582d5A085795f4baDbaC3ff36d1Bcb", "symbol": "CLANKER", "name": "tokenbot",
     "creator_handle": "clankeronbase"},
    {"address": "0x768BE13e1680b5ebE0024C42c896E3dB59ec0149", "symbol": "SKI", "name": "Ski Mask Dog",
     "creator_handle": "basedmemes"},
    {"address": "0x6921B130D297cc43754afba22e5EAc0FBf8Db75b", "symbol": "DOGINME", "name": "doginme",
     "creator_handle": "luca_netz"},
    {"address": "0x9a26F5433671751C3276a065f57e5a02D2817973", "symbol": "KEYCAT", "name": "Keyboard Cat",
     "creator_handle": "degenspartan"},
    {"address": "0x3849cC93e7B71b37885237cd91a215974135cA8c", "symbol": "AGENT", "name": "Agent Genesis",
     "creator_handle": "saylor_ai"},
    {"address": "0x55cD6469F597452B5A7536e2CD98fDE4c1247ee4", "symbol": "FROG", "name": "Frogman",
     "creator_handle": "fartcoin_agent"},
    {"address": "0x06f71FB90f84b35302D132322A3c90E4477333B0", "symbol": "BANK", "name": "Bankr Index",
     "creator_handle": "tokenterminal"},
    {"address": "0xb1a03EdA10342529bBF8EB700a06C60441fEf25d", "symbol": "MIGGLES", "name": "Mister Miggles",
     "creator_handle": "punk6529ai"},
]


def _seed_token_to_doc(t: Dict[str, Any]) -> Dict[str, Any]:
    creator = next((c for c in SEED_CREATORS if c["handle"] == t["creator_handle"]), SEED_CREATORS[0])
    return {
        "id": str(uuid.uuid4()),
        "address": t["address"].lower(),
        "symbol": t["symbol"],
        "name": t["name"],
        "creator_handle": t["creator_handle"],
        "creator_avatar": creator["avatar"],
        "chain": "base",
        "launched_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(15, 120))).isoformat(),
        "total_claimed_eth": round(random.uniform(0.5, 80.0), 4),
        "total_claimed_usd": 0.0,
        "claimable_eth": round(random.uniform(0.01, 4.0), 4),
        "last_polled": now_iso(),
    }


# ============================================================
# HELPERS
# ============================================================

ETH_PRICE_USD = 3450.0  # baseline (refreshed by poller)


def _rand_tx_hash() -> str:
    return "0x" + "".join(random.choices("abcdef0123456789", k=64))


def _rand_wallet() -> str:
    return "0x" + "".join(random.choices("abcdef0123456789", k=40))


async def fetch_eth_price() -> float:
    """Fetch real ETH price from CoinGecko (no key required)."""
    global ETH_PRICE_USD
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
            )
            data = r.json()
            ETH_PRICE_USD = float(data["ethereum"]["usd"])
            logger.info(f"ETH price updated: ${ETH_PRICE_USD}")
    except Exception as e:
        logger.warning(f"Failed to fetch ETH price: {e}")
    return ETH_PRICE_USD


async def fetch_bankr_fees(token_address: str) -> Optional[Dict[str, Any]]:
    """Public Bankr token fees endpoint (unauthenticated)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.get(
                f"https://api.bankr.bot/token-launches/{token_address}/fees",
                params={"days": 30},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug(f"Bankr API miss for {token_address}: {e}")
    return None


async def seed_database():
    """Seed tokens + initial claim events if collection is empty."""
    tokens_count = await db.tokens.count_documents({})
    if tokens_count == 0:
        docs = [_seed_token_to_doc(t) for t in SEED_TOKENS]
        for d in docs:
            d["total_claimed_usd"] = round(d["total_claimed_eth"] * ETH_PRICE_USD, 2)
        await db.tokens.insert_many(docs)
        logger.info(f"Seeded {len(docs)} tokens")

    events_count = await db.claim_events.count_documents({})
    if events_count == 0:
        tokens = await db.tokens.find({}, {"_id": 0}).to_list(100)
        events = []
        now = datetime.now(timezone.utc)
        for _ in range(120):
            tok = random.choice(tokens)
            claimer = random.choice(SEED_CREATORS)
            amt_eth = round(random.uniform(0.005, 2.8), 5)
            ts = now - timedelta(minutes=random.randint(2, 60 * 24 * 21))
            events.append({
                "id": str(uuid.uuid4()),
                "token_address": tok["address"],
                "token_symbol": tok["symbol"],
                "token_name": tok["name"],
                "claimer_handle": claimer["handle"],
                "claimer_avatar": claimer["avatar"],
                "claimer_wallet": _rand_wallet(),
                "amount_eth": amt_eth,
                "amount_usd": round(amt_eth * ETH_PRICE_USD, 2),
                "tx_hash": _rand_tx_hash(),
                "block_number": random.randint(20_000_000, 22_500_000),
                "chain": "base",
                "timestamp": ts.isoformat(),
            })
        await db.claim_events.insert_many(events)
        logger.info(f"Seeded {len(events)} historical claim events")


async def generate_live_event() -> Optional[Dict[str, Any]]:
    """Generate a realistic new claim event (combination of polled + simulated)."""
    tokens = await db.tokens.find({}, {"_id": 0}).to_list(200)
    if not tokens:
        return None
    tok = random.choice(tokens)

    # 30% chance: try to use real Bankr API data shape
    real = None
    if random.random() < 0.3:
        real = await fetch_bankr_fees(tok["address"])

    claimer = random.choice(SEED_CREATORS)
    if random.random() < 0.6:
        # creator claims their own fees most often
        claimer = next((c for c in SEED_CREATORS if c["handle"] == tok["creator_handle"]), claimer)

    if real and isinstance(real, dict):
        try:
            claimable = float(real.get("claimable", {}).get("eth", random.uniform(0.01, 1.5)))
            amt_eth = max(0.001, claimable * random.uniform(0.4, 1.0))
        except Exception:
            amt_eth = round(random.uniform(0.005, 1.8), 5)
    else:
        amt_eth = round(random.uniform(0.005, 1.8), 5)

    event = {
        "id": str(uuid.uuid4()),
        "token_address": tok["address"],
        "token_symbol": tok["symbol"],
        "token_name": tok["name"],
        "claimer_handle": claimer["handle"],
        "claimer_avatar": claimer["avatar"],
        "claimer_wallet": _rand_wallet(),
        "amount_eth": round(amt_eth, 5),
        "amount_usd": round(amt_eth * ETH_PRICE_USD, 2),
        "tx_hash": _rand_tx_hash(),
        "block_number": random.randint(22_400_000, 22_600_000),
        "chain": "base",
        "timestamp": now_iso(),
    }

    # increase token totals
    await db.tokens.update_one(
        {"address": tok["address"]},
        {
            "$inc": {
                "total_claimed_eth": event["amount_eth"],
                "total_claimed_usd": event["amount_usd"],
            },
            "$set": {"last_polled": now_iso()},
        },
    )
    await db.claim_events.insert_one(event)
    return event


# ============================================================
# BACKGROUND POLLER
# ============================================================

_poller_task: Optional[asyncio.Task] = None


async def background_poller():
    """Periodically simulate new claim events + refresh ETH price."""
    logger.info("Background poller started")
    tick = 0
    while True:
        try:
            if tick % 20 == 0:
                await fetch_eth_price()
            # 1-3 new events per cycle
            for _ in range(random.randint(1, 3)):
                ev = await generate_live_event()
                if ev:
                    logger.info(f"New claim: @{ev['claimer_handle']} claimed {ev['amount_eth']} ETH from ${ev['token_symbol']}")
            tick += 1
        except Exception as e:
            logger.error(f"Poller error: {e}")
        await asyncio.sleep(15)


# ============================================================
# ROUTES
# ============================================================


@api_router.get("/")
async def root():
    return {"service": "bankr-bot-claim-monitor", "version": "1.0.0", "chain": "base"}


@api_router.get("/stats")
async def get_stats():
    """Aggregate KPIs."""
    total_events = await db.claim_events.count_documents({})

    pipeline_total = [
        {"$group": {"_id": None,
                    "total_eth": {"$sum": "$amount_eth"},
                    "total_usd": {"$sum": "$amount_usd"}}}
    ]
    agg = await db.claim_events.aggregate(pipeline_total).to_list(1)
    total_eth = float(agg[0]["total_eth"]) if agg else 0.0
    total_usd = float(agg[0]["total_usd"]) if agg else 0.0

    # 24h claims
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    last_24h = await db.claim_events.count_documents({"timestamp": {"$gte": since}})

    pipeline_24h = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": None,
                    "eth": {"$sum": "$amount_eth"},
                    "usd": {"$sum": "$amount_usd"}}}
    ]
    agg24 = await db.claim_events.aggregate(pipeline_24h).to_list(1)
    eth_24h = float(agg24[0]["eth"]) if agg24 else 0.0
    usd_24h = float(agg24[0]["usd"]) if agg24 else 0.0

    unique_claimers = len(await db.claim_events.distinct("claimer_handle"))
    tracked_tokens = await db.tokens.count_documents({})

    return {
        "total_claims": total_events,
        "total_eth": round(total_eth, 4),
        "total_usd": round(total_usd, 2),
        "claims_24h": last_24h,
        "eth_24h": round(eth_24h, 4),
        "usd_24h": round(usd_24h, 2),
        "unique_claimers": unique_claimers,
        "tracked_tokens": tracked_tokens,
        "eth_price_usd": round(ETH_PRICE_USD, 2),
    }


@api_router.get("/claims/feed")
async def claims_feed(
    limit: int = Query(30, ge=1, le=100),
    skip: int = Query(0, ge=0),
    handle: Optional[str] = None,
    token: Optional[str] = None,
):
    """Paginated newest-first feed."""
    query: Dict[str, Any] = {}
    if handle:
        query["claimer_handle"] = {"$regex": f"^{handle}", "$options": "i"}
    if token:
        query["$or"] = [
            {"token_symbol": {"$regex": token, "$options": "i"}},
            {"token_address": token.lower()},
        ]
    cur = db.claim_events.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    items = await cur.to_list(limit)
    return {"items": items, "count": len(items)}


@api_router.get("/leaderboard")
async def leaderboard(limit: int = Query(10, ge=1, le=50)):
    """Top claimers by total ETH claimed."""
    pipeline = [
        {"$group": {
            "_id": "$claimer_handle",
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
    leaderboard_data = []
    for i, r in enumerate(rows):
        leaderboard_data.append({
            "rank": i + 1,
            "handle": r["_id"],
            "avatar": r.get("avatar"),
            "total_eth": round(float(r["total_eth"]), 4),
            "total_usd": round(float(r["total_usd"]), 2),
            "claim_count": int(r["claim_count"]),
            "last_claim": r.get("last_claim"),
        })
    return {"items": leaderboard_data}


@api_router.get("/tokens")
async def list_tokens(limit: int = Query(50, ge=1, le=200)):
    cur = db.tokens.find({}, {"_id": 0}).sort("total_claimed_eth", -1).limit(limit)
    items = await cur.to_list(limit)
    return {"items": items}


@api_router.get("/tokens/{address}")
async def token_detail(address: str):
    tok = await db.tokens.find_one({"address": address.lower()}, {"_id": 0})
    if not tok:
        raise HTTPException(status_code=404, detail="token not found")

    # daily timeline (14 days)
    since = datetime.now(timezone.utc) - timedelta(days=14)
    pipeline = [
        {"$match": {"token_address": address.lower(), "timestamp": {"$gte": since.isoformat()}}},
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
        {"date": t["_id"], "eth": round(float(t["eth"]), 4),
         "usd": round(float(t["usd"]), 2), "count": int(t["count"])}
        for t in timeline
    ]

    recent = await db.claim_events.find(
        {"token_address": address.lower()}, {"_id": 0}
    ).sort("timestamp", -1).limit(15).to_list(15)

    # try to enrich with live Bankr API data
    bankr_live = await fetch_bankr_fees(address)

    return {
        "token": tok,
        "timeline": timeline_data,
        "recent_claims": recent,
        "bankr_live": bankr_live,
    }


@api_router.post("/tokens/track")
async def track_token(payload: TokenCreate):
    addr = payload.address.lower().strip()
    if not addr.startswith("0x") or len(addr) != 42:
        raise HTTPException(status_code=400, detail="invalid base address")

    existing = await db.tokens.find_one({"address": addr}, {"_id": 0})
    if existing:
        return {"status": "exists", "token": existing}

    # Try to enrich from Bankr
    bankr = await fetch_bankr_fees(addr)
    symbol = payload.symbol or (bankr or {}).get("token", {}).get("symbol") or "TOKEN"
    name = payload.name or (bankr or {}).get("token", {}).get("name") or "Unknown Token"
    handle = payload.creator_handle or (bankr or {}).get("creator", {}).get("xUsername") or "unknown"

    creator = next((c for c in SEED_CREATORS if c["handle"] == handle), {
        "handle": handle,
        "avatar": f"https://api.dicebear.com/9.x/identicon/svg?seed={handle}&backgroundColor=00FF66",
    })

    claimed_eth = 0.0
    claimable_eth = 0.0
    if bankr:
        try:
            claimed_eth = float(bankr.get("claimed", {}).get("eth", 0) or 0)
            claimable_eth = float(bankr.get("claimable", {}).get("eth", 0) or 0)
        except Exception:
            pass

    doc = {
        "id": str(uuid.uuid4()),
        "address": addr,
        "symbol": symbol.upper(),
        "name": name,
        "creator_handle": handle,
        "creator_avatar": creator["avatar"],
        "chain": "base",
        "launched_at": now_iso(),
        "total_claimed_eth": claimed_eth,
        "total_claimed_usd": round(claimed_eth * ETH_PRICE_USD, 2),
        "claimable_eth": claimable_eth,
        "last_polled": now_iso(),
    }
    await db.tokens.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "added", "token": doc}


@api_router.get("/search")
async def search(q: str = Query(..., min_length=1)):
    """Search across handles + tokens."""
    qrx = {"$regex": q, "$options": "i"}
    claimers = await db.claim_events.aggregate([
        {"$match": {"claimer_handle": qrx}},
        {"$group": {"_id": "$claimer_handle", "avatar": {"$first": "$claimer_avatar"},
                    "total_eth": {"$sum": "$amount_eth"}, "count": {"$sum": 1}}},
        {"$limit": 10},
    ]).to_list(10)

    tokens = await db.tokens.find(
        {"$or": [{"symbol": qrx}, {"name": qrx}, {"address": q.lower()}]},
        {"_id": 0},
    ).limit(10).to_list(10)

    return {
        "claimers": [
            {"handle": c["_id"], "avatar": c.get("avatar"),
             "total_eth": round(float(c["total_eth"]), 4), "count": int(c["count"])}
            for c in claimers
        ],
        "tokens": tokens,
    }


@api_router.get("/handle/{handle}")
async def claimer_detail(handle: str):
    """Detail page for a Twitter handle."""
    events = await db.claim_events.find(
        {"claimer_handle": handle}, {"_id": 0}
    ).sort("timestamp", -1).limit(50).to_list(50)

    if not events:
        raise HTTPException(status_code=404, detail="no claims found for handle")

    total_eth = sum(e["amount_eth"] for e in events)
    total_usd = sum(e["amount_usd"] for e in events)
    avatar = events[0].get("claimer_avatar")
    tokens_claimed = list({e["token_symbol"] for e in events})

    return {
        "handle": handle,
        "avatar": avatar,
        "total_eth": round(total_eth, 4),
        "total_usd": round(total_usd, 2),
        "claim_count": len(events),
        "tokens_claimed": tokens_claimed,
        "claims": events,
    }


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    global _poller_task
    await fetch_eth_price()
    await seed_database()
    _poller_task = asyncio.create_task(background_poller())
    logger.info("Bankr monitor startup complete")


@app.on_event("shutdown")
async def shutdown_db_client():
    global _poller_task
    if _poller_task:
        _poller_task.cancel()
    client.close()
