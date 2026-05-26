import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy, ExternalLink } from "lucide-react";
import { api, formatEth, formatUsd } from "@/lib/api";

export default function LifetimeLeaderboard({ limit = 12 }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await api.get(`/leaderboard/lifetime?limit=${limit}`);
        setRows(r.data.items);
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [limit]);

  const accent = (i) => {
    if (i === 0) return "text-[#FFE600] glow-cyan";
    if (i === 1) return "text-[#00F0FF]";
    if (i === 2) return "text-[#FF007A]";
    return "text-[#8A8A93]";
  };

  return (
    <div className="panel corners" data-testid="lifetime-leaderboard">
      <div className="flex items-center justify-between p-4 border-b border-[#00FF66]/20">
        <div className="flex items-center gap-2">
          <Trophy size={14} className="text-[#FFE600]" />
          <div className="text-head text-sm tracking-[0.2em] uppercase">
            Lifetime Top Creators
          </div>
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest">via BANKR API</div>
      </div>
      <div className="divide-y divide-[#00FF66]/10">
        {loading && (
          <div className="p-6 text-xs text-[#52525B]">
            <span className="blink">Computing lifetime totals</span>
          </div>
        )}
        {!loading && rows.length === 0 && (
          <div className="p-6 text-xs text-[#52525B]">
            Polling Bankr API for token earnings...
          </div>
        )}
        {rows.map((r, i) => {
          const display = r.handle ? `@${r.handle}` : (r.wallet ? `${r.wallet.slice(0,6)}…${r.wallet.slice(-4)}` : "anonymous");
          return (
          <Link
            key={`${r.handle || r.wallet || i}`}
            to={r.handle ? `/handle/${r.handle}` : (r.wallet ? `/wallet/${r.wallet}` : "#")}
            data-testid={`lifetime-row-${r.handle || r.wallet}`}
            className="flex items-center gap-3 p-3 hover:bg-[#00FF66]/5 transition-colors group"
          >
            <div className={`w-7 text-center text-xs font-bold ${accent(i)}`}>
              #{r.rank}
            </div>
            <img
              src={r.avatar || `https://api.dicebear.com/9.x/identicon/svg?seed=${r.wallet || r.handle}&backgroundColor=00FF66`}
              alt={r.handle || r.wallet}
              className="w-9 h-9 border border-[#00FF66]/30 bg-[#0F0F13]"
              onError={(ev) => {
                ev.target.src = `https://api.dicebear.com/9.x/identicon/svg?seed=${r.wallet || r.handle}&backgroundColor=00FF66`;
              }}
            />
            <div className="flex-1 min-w-0">
              <div className="text-white text-sm font-medium truncate group-hover:text-[#00FF66] transition-colors">
                {display}
              </div>
              <div className="text-[10px] text-[#52525B] tracking-wide">
                {r.tokens} token{r.tokens !== 1 ? "s" : ""} · {r.claim_count} claims
              </div>
            </div>
            <div className="text-right">
              <div className="text-[#00FF66] text-sm font-semibold glow-green">
                {formatEth(r.lifetime_eth)} Ξ
              </div>
              <div className="text-[10px] text-[#8A8A93]">{formatUsd(r.lifetime_usd)}</div>
            </div>
          </Link>
          );
        })}
      </div>
    </div>
  );
}
