import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, ArrowUpRight } from "lucide-react";
import { getFeed, formatEth, formatUsd, shortAddress, timeAgo } from "@/lib/api";
import { Input } from "@/components/ui/input";

export default function LiveFeed() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [handleFilter, setHandleFilter] = useState("");
  const [tokenFilter, setTokenFilter] = useState("");
  const [newIds, setNewIds] = useState(new Set());

  const load = async () => {
    try {
      const data = await getFeed({
        limit: 40,
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
          setTimeout(() => setNewIds(new Set()), 1500);
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

      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="feed-table">
          <thead>
            <tr className="text-[10px] tracking-[0.2em] uppercase text-[#8A8A93] border-b border-[#00FF66]/20">
              <th className="text-left py-3 px-4">Claimer</th>
              <th className="text-left py-3 px-4">Token</th>
              <th className="text-right py-3 px-4">Amount</th>
              <th className="text-right py-3 px-4 hidden md:table-cell">USD Value</th>
              <th className="text-left py-3 px-4 hidden lg:table-cell">Wallet</th>
              <th className="text-right py-3 px-4">Time</th>
              <th className="text-right py-3 px-4">Tx</th>
            </tr>
          </thead>
          <tbody>
            {loading && events.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center py-12 text-[#52525B] text-xs">
                  <span className="blink">Loading stream</span>
                </td>
              </tr>
            )}
            {!loading && events.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center py-12 text-[#52525B] text-xs">
                  No claims match your filter.
                </td>
              </tr>
            )}
            {events.map((e) => (
              <tr
                key={e.id}
                data-testid={`feed-row-${e.id}`}
                className={`border-b border-[#00FF66]/10 hover:bg-[#00FF66]/5 transition-colors ${
                  newIds.has(e.id) ? "row-new" : ""
                }`}
              >
                <td className="py-3 px-4">
                  <Link
                    to={`/handle/${e.claimer_handle}`}
                    className="flex items-center gap-2 group"
                    data-testid={`claimer-link-${e.claimer_handle}`}
                  >
                    <img
                      src={e.claimer_avatar}
                      alt={e.claimer_handle}
                      className="w-7 h-7 border border-[#00FF66]/40 bg-[#0F0F13]"
                    />
                    <div className="leading-tight">
                      <div className="text-white font-medium group-hover:text-[#00FF66] transition-colors">
                        @{e.claimer_handle}
                      </div>
                      <div className="text-[10px] text-[#52525B]">x.com</div>
                    </div>
                  </Link>
                </td>
                <td className="py-3 px-4">
                  <Link to={`/tokens/${e.token_address}`} className="group" data-testid={`token-link-${e.token_symbol}`}>
                    <div className="text-[#00F0FF] font-semibold group-hover:glow-cyan">
                      ${e.token_symbol}
                    </div>
                    <div className="text-[10px] text-[#52525B] truncate max-w-[180px]">
                      {e.token_name}
                    </div>
                  </Link>
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="text-[#00FF66] font-semibold glow-green">
                    {formatEth(e.amount_eth)} Ξ
                  </div>
                </td>
                <td className="py-3 px-4 text-right hidden md:table-cell">
                  <span className="text-white">{formatUsd(e.amount_usd)}</span>
                </td>
                <td className="py-3 px-4 text-xs text-[#8A8A93] hidden lg:table-cell">
                  {shortAddress(e.claimer_wallet)}
                </td>
                <td className="py-3 px-4 text-right text-xs text-[#8A8A93]">
                  {timeAgo(e.timestamp)} ago
                </td>
                <td className="py-3 px-4 text-right">
                  <a
                    href={`https://basescan.org/tx/${e.tx_hash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`tx-link-${e.tx_hash.slice(0, 10)}`}
                    className="inline-flex items-center gap-1 text-[#8A8A93] hover:text-[#00FF66] transition-colors"
                  >
                    <span className="hidden sm:inline text-xs">{shortAddress(e.tx_hash)}</span>
                    <ExternalLink size={12} />
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
