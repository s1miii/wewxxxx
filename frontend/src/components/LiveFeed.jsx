import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, PartyPopper } from "lucide-react";
import { getFeed, formatEth, formatUsd, shortAddress, timeAgo } from "@/lib/api";
import { Input } from "@/components/ui/input";

function fmtUsdCompact(v) {
  v = Number(v || 0);
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(2)}K`;
  return `$${v.toFixed(2)}`;
}

export default function LiveFeed() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [handleFilter, setHandleFilter] = useState("");
  const [tokenFilter, setTokenFilter] = useState("");
  const [newIds, setNewIds] = useState(new Set());

  const load = async () => {
    try {
      const data = await getFeed({
        limit: 30,
        handle: handleFilter || undefined,
        token: tokenFilter || undefined,
      });
      setEvents((prev) => {
        const prevIds = new Set(prev.map((p) => p.id));
        const nextNew = new Set(
          data.items.filter((e) => !prevIds.has(e.id)).map((e) => e.id)
        );
        if (prev.length > 0 && nextNew.size > 0) {
          setNewIds(nextNew);
          setTimeout(() => setNewIds(new Set()), 2000);
        }
        return data.items;
      });
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, [handleFilter, tokenFilter]);

  return (
    <div className="panel corners" data-testid="live-feed">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-b border-[#00FF66]/20">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 bg-[#00FF66] pulse-dot rounded-full"></div>
          <div className="text-head text-sm tracking-[0.2em] uppercase text-white">
            Live Claim Stream
          </div>
          <span className="text-xs text-[#52525B]">{events.length} events</span>
        </div>
        <div className="flex items-center gap-2">
          <Input
            data-testid="filter-handle-input"
            value={handleFilter}
            onChange={(e) => setHandleFilter(e.target.value)}
            placeholder="@handle"
            className="h-8 w-32 rounded-none bg-[#050505] border-[#00FF66]/30 text-xs font-mono focus-visible:border-[#00FF66] focus-visible:ring-0"
          />
          <Input
            data-testid="filter-token-input"
            value={tokenFilter}
            onChange={(e) => setTokenFilter(e.target.value)}
            placeholder="$TOKEN"
            className="h-8 w-32 rounded-none bg-[#050505] border-[#00FF66]/30 text-xs font-mono focus-visible:border-[#00FF66] focus-visible:ring-0"
          />
        </div>
      </div>

      <div className="divide-y divide-[#00FF66]/10 max-h-[1400px] overflow-y-auto" data-testid="feed-list">
        {loading && events.length === 0 && (
          <div className="p-12 text-center text-[#52525B] text-xs">
            <span className="blink">Backfilling Released events from Base</span>
          </div>
        )}
        {!loading && events.length === 0 && (
          <div className="p-12 text-center text-[#52525B] text-xs">
            No claims match your filter — waiting for next on-chain claim…
          </div>
        )}

        {events.map((e) => (
          <ClaimCard key={e.id} e={e} isNew={newIds.has(e.id)} />
        ))}
      </div>
    </div>
  );
}

function ClaimCard({ e, isNew }) {
  const linkClaimer = e.claimer_handle
    ? `/handle/${e.claimer_handle}`
    : `/wallet/${e.beneficiary || e.claimer_wallet}`;
  const displayName = e.claimer_handle
    ? `@${e.claimer_handle}`
    : shortAddress(e.beneficiary || e.claimer_wallet);

  return (
    <div
      className={`p-4 ${isNew ? "row-new" : ""} hover:bg-[#00FF66]/[0.03] transition-colors`}
      data-testid={`feed-row-${e.id}`}
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-2 text-[10px] tracking-[0.25em] uppercase text-[#FFE600]">
          <PartyPopper size={12} />
          <span className="glow-cyan">NEW BANKR FEE CLAIMED</span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-[#52525B]">
          <a
            href={`https://basescan.org/tx/${e.tx_hash}`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`tx-link-${e.tx_hash.slice(0, 10)}`}
            className="hover:text-[#00FF66] inline-flex items-center gap-1"
          >
            {shortAddress(e.tx_hash)} <ExternalLink size={10} />
          </a>
          <span>{timeAgo(e.timestamp)} ago</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        {/* Token info */}
        <div className="space-y-1.5 text-xs">
          <div className="text-[10px] tracking-widest text-[#00F0FF] uppercase mb-1">
            Token Information
          </div>
          <Row label="Name" value={e.token_name || "?"} />
          <Row label="Symbol">
            <Link
              to={e.token_address ? `/tokens/${e.token_address}` : "#"}
              className="text-[#00F0FF] hover:underline font-semibold"
              data-testid={`token-link-${e.token_symbol}`}
            >
              ${e.token_symbol}
            </Link>
          </Row>
          <Row label="Contract">
            {e.token_address ? (
              <a
                href={`https://basescan.org/token/${e.token_address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#8A8A93] hover:text-[#00FF66] font-mono"
              >
                {shortAddress(e.token_address)}
              </a>
            ) : (
              <span className="text-[#52525B]">—</span>
            )}
          </Row>
          <Row label="Market Cap" value={fmtUsdCompact(e.market_cap_usd)} valueClass="text-[#FFE600]" />
          <Row label="Liquidity" value={fmtUsdCompact(e.liquidity_usd)} valueClass="text-[#00F0FF]" />
        </div>

        {/* Beneficiary + claim amounts */}
        <div className="space-y-1.5 text-xs">
          <div className="text-[10px] tracking-widest text-[#00FF66] uppercase mb-1">
            Released to Beneficiary
          </div>
          <Row label="Token Amount">
            <span className="text-white font-semibold">
              {Number(e.released_token_amount || 0).toLocaleString(undefined, {
                maximumFractionDigits: 4,
              })}{" "}
              ${e.token_symbol}
            </span>
          </Row>
          <Row label="ETH Amount">
            <span className="text-[#00FF66] font-semibold glow-green">
              {formatEth(e.released_weth_amount)} ETH
            </span>
            <span className="text-[#52525B] ml-1">({formatUsd(e.released_usd)})</span>
          </Row>
          <Row label="Beneficiary">
            <Link
              to={linkClaimer}
              className="inline-flex items-center gap-1.5 group"
              data-testid={`claimer-link-${e.claimer_handle || e.beneficiary}`}
            >
              {e.claimer_avatar && (
                <img
                  src={e.claimer_avatar}
                  alt=""
                  className="w-4 h-4 border border-[#00FF66]/30"
                  onError={(ev) => {
                    ev.target.style.display = "none";
                  }}
                />
              )}
              <span className="text-white group-hover:text-[#00FF66] font-medium">
                {displayName}
              </span>
              {e.claimer_handle && (
                <span className="text-[10px] text-[#52525B]">
                  · {shortAddress(e.beneficiary)}
                </span>
              )}
            </Link>
          </Row>
          {e.tweet_url && (
            <Row label="Tweet">
              <a
                href={e.tweet_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#00F0FF] hover:underline text-[10px]"
              >
                view post →
              </a>
            </Row>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, children, valueClass = "text-white" }) {
  return (
    <div className="flex items-baseline gap-2 leading-tight">
      <span className="text-[10px] tracking-wider text-[#52525B] uppercase shrink-0 w-24">
        {label}
      </span>
      {children !== undefined ? (
        children
      ) : (
        <span className={`text-xs ${valueClass}`}>{value}</span>
      )}
    </div>
  );
}
