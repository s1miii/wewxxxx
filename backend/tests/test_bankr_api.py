"""Backend tests for Bankr Bot Claim Fee Monitor API."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://twitter-claim-watch.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Root + Stats ----------
class TestRootAndStats:
    def test_root(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("service") == "bankr-bot-claim-monitor"
        assert data.get("chain") == "base"

    def test_stats_shape(self, client):
        r = client.get(f"{API}/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ["total_claims", "total_eth", "unique_claimers", "claims_24h", "eth_price_usd"]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["total_claims"], int)
        assert d["total_claims"] > 0
        assert d["eth_price_usd"] > 0


# ---------- Feed ----------
class TestFeed:
    def test_feed_default(self, client):
        r = client.get(f"{API}/claims/feed")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        assert len(d["items"]) > 0
        ev = d["items"][0]
        for k in ["claimer_handle", "token_symbol", "amount_eth", "tx_hash", "timestamp"]:
            assert k in ev

    def test_feed_filter_by_handle(self, client):
        # use a seed handle prefix
        r = client.get(f"{API}/claims/feed", params={"handle": "aixbt"})
        assert r.status_code == 200
        items = r.json()["items"]
        for it in items:
            assert it["claimer_handle"].lower().startswith("aixbt")

    def test_feed_filter_by_token(self, client):
        r = client.get(f"{API}/claims/feed", params={"token": "BNKR"})
        assert r.status_code == 200
        items = r.json()["items"]
        # may or may not have items, but if any, symbol contains BNKR
        for it in items:
            assert "BNKR" in it["token_symbol"].upper()

    def test_feed_pagination(self, client):
        r = client.get(f"{API}/claims/feed", params={"limit": 5})
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 5


# ---------- Leaderboard ----------
class TestLeaderboard:
    def test_leaderboard_sorted(self, client):
        r = client.get(f"{API}/leaderboard")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        eths = [i["total_eth"] for i in items]
        assert eths == sorted(eths, reverse=True)
        # rank field
        assert items[0]["rank"] == 1


# ---------- Tokens ----------
class TestTokens:
    def test_list_tokens(self, client):
        r = client.get(f"{API}/tokens")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 10
        t = items[0]
        for k in ["address", "symbol", "creator_handle", "total_claimed_eth"]:
            assert k in t

    def test_token_detail(self, client):
        list_r = client.get(f"{API}/tokens").json()["items"]
        addr = list_r[0]["address"]
        r = client.get(f"{API}/tokens/{addr}")
        assert r.status_code == 200
        d = r.json()
        assert "token" in d
        assert "timeline" in d
        assert "recent_claims" in d
        assert d["token"]["address"] == addr

    def test_token_detail_404(self, client):
        r = client.get(f"{API}/tokens/0x0000000000000000000000000000000000000000")
        assert r.status_code == 404

    def test_track_token_invalid(self, client):
        r = client.post(f"{API}/tokens/track", json={"address": "notavalidaddr"})
        assert r.status_code == 400

    def test_track_token_valid_then_exists(self, client):
        addr = "0x" + "ab" * 20  # 42 chars valid format
        r1 = client.post(f"{API}/tokens/track", json={"address": addr, "symbol": "TST", "name": "TestTok", "creator_handle": "TEST_user"})
        assert r1.status_code == 200
        assert r1.json()["status"] in ("added", "exists")

        r2 = client.post(f"{API}/tokens/track", json={"address": addr})
        assert r2.status_code == 200
        assert r2.json()["status"] == "exists"


# ---------- Search ----------
class TestSearch:
    def test_search_handle(self, client):
        r = client.get(f"{API}/search", params={"q": "aixbt"})
        assert r.status_code == 200
        d = r.json()
        assert "claimers" in d and "tokens" in d
        assert any("aixbt" in c["handle"].lower() for c in d["claimers"])

    def test_search_token(self, client):
        r = client.get(f"{API}/search", params={"q": "BNKR"})
        assert r.status_code == 200
        d = r.json()
        assert any(t["symbol"] == "BNKR" for t in d["tokens"])


# ---------- Handle profile ----------
class TestHandle:
    def test_handle_profile(self, client):
        # find a handle from leaderboard
        lb = client.get(f"{API}/leaderboard").json()["items"]
        handle = lb[0]["handle"]
        r = client.get(f"{API}/handle/{handle}")
        assert r.status_code == 200
        d = r.json()
        for k in ["handle", "total_eth", "claim_count", "tokens_claimed", "claims"]:
            assert k in d
        assert d["claim_count"] > 0
        assert isinstance(d["tokens_claimed"], list)

    def test_handle_404(self, client):
        r = client.get(f"{API}/handle/nonexistent_handle_xyz_12345")
        assert r.status_code == 404


# ---------- Background poller ----------
class TestPoller:
    def test_poller_increments(self, client):
        s1 = client.get(f"{API}/stats").json()["total_claims"]
        time.sleep(22)  # poller runs every 15s
        s2 = client.get(f"{API}/stats").json()["total_claims"]
        assert s2 > s1, f"Background poller did not generate events: before={s1} after={s2}"
