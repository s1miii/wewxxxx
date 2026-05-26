import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ExternalLink, Twitter } from "lucide-react";
import { getClaimerDetail, formatEth, formatUsd, shortAddress, timeAgo } from "@/lib/api";

export default function ClaimerDetail() {
  const { handle } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const d = await getClaimerDetail(handle);
        setData(d);
      } catch (e) {
        setErr(e?.response?.data?.detail || "Failed to load");
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [handle]);

  if (loading) return <div className="text-[#52525B] blink text-xs">Loading profile</div>;
  if (err) return <div className="text-[#FF007A] text-sm">{err}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6" data-testid="claimer-detail-page">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-xs text-[#8A8A93] hover:text-[#00FF66] transition-colors"
      >
        <ArrowLeft size={12} /> BACK
      </Link>

      <div className="panel corners p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <img
              src={data.avatar}
              alt={data.handle}
              className="w-16 h-16 border border-[#00FF66] glow-green"
            />
            <div>
              <h1 className="text-head text-3xl font-bold text-white tracking-tighter">
                @{data.handle}
              </h1>
              <a
                href={`https://x.com/${data.handle}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 mt-1 text-xs text-[#00F0FF] hover:underline"
                data-testid="x-profile-link"
              >
                <Twitter size={12} /> View on x.com <ExternalLink size={10} />
              </a>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-6 text-right">
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Total ETH</div>
              <div className="text-[#00FF66] text-xl font-bold glow-green">{formatEth(data.total_eth)}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">USD</div>
              <div className="text-white text-xl font-bold">{formatUsd(data.total_usd)}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Claims</div>
              <div className="text-[#FFE600] text-xl font-bold">{data.claim_count}</div>
            </div>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-[#00FF66]/10">
          <div className="text-[10px] tracking-widest text-[#52525B] uppercase mb-2">Tokens Claimed</div>
          <div className="flex flex-wrap gap-2">
            {data.tokens_claimed.map((s) => (
              <span
                key={s}
                className="px-2 py-1 border border-[#00F0FF]/40 text-[#00F0FF] text-xs font-mono"
              >
                ${s}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="panel corners">
        <div className="p-4 border-b border-[#00FF66]/20 text-head text-sm tracking-[0.2em] uppercase">
          Claim History
        </div>
        <div className="divide-y divide-[#00FF66]/10">
          {data.claims.map((c) => (
            <div
              key={c.id}
              className="flex items-center gap-4 p-3 hover:bg-[#00FF66]/5"
              data-testid={`claim-history-${c.id}`}
            >
              <Link to={`/tokens/${c.token_address}`} className="flex-1 min-w-0">
                <div className="text-[#00F0FF] font-semibold">${c.token_symbol}</div>
                <div className="text-[10px] text-[#52525B] truncate">{c.token_name}</div>
              </Link>
              <div className="text-right">
                <div className="text-[#00FF66] font-semibold">{formatEth(c.amount_eth)} Ξ</div>
                <div className="text-[10px] text-[#52525B]">{formatUsd(c.amount_usd)}</div>
              </div>
              <div className="text-right text-xs text-[#8A8A93] w-20">
                {timeAgo(c.timestamp)} ago
              </div>
              <a
                href={`https://basescan.org/tx/${c.tx_hash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#8A8A93] hover:text-[#00FF66]"
              >
                <ExternalLink size={12} />
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
