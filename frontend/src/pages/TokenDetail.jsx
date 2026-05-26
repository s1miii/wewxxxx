import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { getTokenDetail, formatEth, formatUsd, shortAddress, timeAgo } from "@/lib/api";

export default function TokenDetail() {
  const { address } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const d = await getTokenDetail(address);
        setData(d);
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [address]);

  if (loading) {
    return <div className="text-[#52525B] text-xs blink">Loading token</div>;
  }
  if (!data) {
    return <div className="text-[#FF007A]">Token not found</div>;
  }

  const { token, timeline, recent_claims } = data;

  return (
    <div className="space-y-6" data-testid="token-detail-page">
      <Link
        to="/tokens"
        className="inline-flex items-center gap-2 text-xs text-[#8A8A93] hover:text-[#00FF66] transition-colors"
      >
        <ArrowLeft size={12} /> BACK TO TOKENS
      </Link>

      <div className="panel corners p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 border border-[#00F0FF] flex items-center justify-center bg-[#0F0F13]">
              <span className="text-head text-lg font-bold text-[#00F0FF] glow-cyan">
                {token.symbol.slice(0, 3)}
              </span>
            </div>
            <div>
              <h1 className="text-head text-3xl font-bold text-white tracking-tighter">
                ${token.symbol}
              </h1>
              <div className="text-sm text-[#8A8A93]">{token.name}</div>
              <Link
                to={`/handle/${token.creator_handle}`}
                className="inline-flex items-center gap-2 mt-1 text-xs text-[#00FF66] hover:underline"
                data-testid="creator-link"
              >
                <img src={token.creator_avatar} className="w-4 h-4" alt="" />
                @{token.creator_handle}
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 text-right">
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Claimed</div>
              <div className="text-[#00FF66] font-bold glow-green">{formatEth(token.total_claimed_eth)} Ξ</div>
              <div className="text-[10px] text-[#52525B]">{formatUsd(token.total_claimed_usd)}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Pending</div>
              <div className="text-[#FFE600] font-bold">{formatEth(token.claimable_eth)} Ξ</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Launched</div>
              <div className="text-white font-bold">{timeAgo(token.launched_at)} ago</div>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-[#00FF66]/10 flex flex-wrap items-center gap-4 text-xs text-[#8A8A93]">
          <span>CHAIN: <span className="text-[#00F0FF]">{token.chain.toUpperCase()}</span></span>
          <a
            href={`https://basescan.org/token/${token.address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 hover:text-[#00FF66]"
          >
            {shortAddress(token.address)} <ExternalLink size={10} />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="panel corners p-4 lg:col-span-2">
          <div className="text-head text-sm tracking-[0.2em] uppercase mb-4">
            Daily Claim Volume · 14d
          </div>
          {timeline.length === 0 ? (
            <div className="text-[#52525B] text-xs py-10 text-center">No recent claims.</div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={timeline}>
                <CartesianGrid stroke="rgba(0,255,102,0.08)" strokeDasharray="2 4" />
                <XAxis dataKey="date" stroke="#52525B" fontSize={10} tickFormatter={(d) => d.slice(5)} />
                <YAxis stroke="#52525B" fontSize={10} />
                <Tooltip
                  contentStyle={{
                    background: "#0F0F13",
                    border: "1px solid rgba(0,255,102,0.4)",
                    borderRadius: 0,
                    fontFamily: "IBM Plex Mono",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "#00FF66" }}
                />
                <Bar dataKey="eth" fill="#00FF66" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="panel corners">
          <div className="p-4 border-b border-[#00FF66]/20 text-head text-sm tracking-[0.2em] uppercase">
            Recent Claims
          </div>
          <div className="divide-y divide-[#00FF66]/10 max-h-[300px] overflow-auto">
            {recent_claims.length === 0 && (
              <div className="p-4 text-xs text-[#52525B]">No claims yet.</div>
            )}
            {recent_claims.map((c) => (
              <Link
                key={c.id}
                to={`/handle/${c.claimer_handle}`}
                className="flex items-center gap-3 p-3 hover:bg-[#00FF66]/5"
              >
                <img src={c.claimer_avatar} alt="" className="w-7 h-7 border border-[#00FF66]/30" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">@{c.claimer_handle}</div>
                  <div className="text-[10px] text-[#52525B]">{timeAgo(c.timestamp)} ago</div>
                </div>
                <div className="text-right">
                  <div className="text-[#00FF66] text-sm font-semibold">{formatEth(c.amount_eth)} Ξ</div>
                  <div className="text-[10px] text-[#52525B]">{formatUsd(c.amount_usd)}</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
