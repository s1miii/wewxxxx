import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Crown } from "lucide-react";
import { getLeaderboard, formatEth, formatUsd, timeAgo } from "@/lib/api";

export default function Leaderboard({ compact = false, limit = 10 }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getLeaderboard(limit);
        setRows(data.items);
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 12000);
    return () => clearInterval(id);
  }, [limit]);

  const accent = (i) => {
    if (i === 0) return "text-[#FFE600] glow-cyan";
    if (i === 1) return "text-[#00F0FF]";
    if (i === 2) return "text-[#FF007A]";
    return "text-[#8A8A93]";
  };

  return (
    <div className="panel corners h-full" data-testid="leaderboard">
      <div className="flex items-center justify-between p-4 border-b border-[#00FF66]/20">
        <div className="flex items-center gap-2">
          <Crown size={14} className="text-[#FFE600]" />
          <div className="text-head text-sm tracking-[0.2em] uppercase">
            Top Claimers
          </div>
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest">BY ETH</div>
      </div>

      <div className="divide-y divide-[#00FF66]/10">
        {loading && (
          <div className="p-6 text-xs text-[#52525B]">
            <span className="blink">Computing rankings</span>
          </div>
        )}
        {rows.map((r, i) => (
          <Link
            key={r.handle}
            to={`/handle/${r.handle}`}
            className="flex items-center gap-3 p-3 hover:bg-[#00FF66]/5 transition-colors group"
            data-testid={`leaderboard-row-${r.handle}`}
          >
            <div className={`w-7 text-center text-xs font-bold ${accent(i)}`}>
              #{r.rank}
            </div>
            <img
              src={r.avatar}
              alt={r.handle}
              className="w-9 h-9 border border-[#00FF66]/30 bg-[#0F0F13]"
            />
            <div className="flex-1 min-w-0">
              <div className="text-white text-sm font-medium truncate group-hover:text-[#00FF66] transition-colors">
                @{r.handle}
              </div>
              <div className="text-[10px] text-[#52525B] tracking-wide">
                {r.claim_count} claim{r.claim_count !== 1 ? "s" : ""} · last {timeAgo(r.last_claim)} ago
              </div>
            </div>
            <div className="text-right">
              <div className="text-[#00FF66] text-sm font-semibold glow-green">
                {formatEth(r.total_eth)} Ξ
              </div>
              {!compact && (
                <div className="text-[10px] text-[#8A8A93]">{formatUsd(r.total_usd)}</div>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
