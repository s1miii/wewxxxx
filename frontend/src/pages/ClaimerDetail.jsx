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
      <Link to="/" className="inline-flex items-center gap-2 text-xs text-[#8A8A93] hover:text-[#00FF66] transition-colors">
        <ArrowLeft size={12} /> BACK
      </Link>

      <div className="panel corners p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <img
              src={data.avatar || `https://unavatar.io/x/${data.handle}`}
              alt={data.handle}
              className="w-16 h-16 border border-[#00FF66] glow-green"
              onError={(ev) => {
                ev.target.src = `https://api.dicebear.com/9.x/identicon/svg?seed=${data.handle}&backgroundColor=00FF66`;
              }}
            />
            <div>
              <h1 className="text-head text-3xl font-bold text-white tracking-tighter">
                @{data.handle}
              </h1>
              <a
                href={data.x_url || `https://x.com/${data.handle}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 mt-1 text-xs text-[#00F0FF] hover:underline"
                data-testid="x-profile-link"
              >
                <Twitter size={12} /> View on x.com <ExternalLink size={10} />
              </a>
              {data.wallet && (
                <a
                  href={`https://basescan.org/address/${data.wallet}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block mt-1 text-[10px] font-mono text-[#52525B] hover:text-[#00FF66]"
                >
                  {shortAddress(data.wallet)}
                </a>
              )}
            </div>
          </div>
          <div className="grid grid-cols-4 gap-4 text-right">
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Lifetime ETH</div>
              <div className="text-[#00FF66] text-xl font-bold glow-green">{formatEth(data.lifetime_eth || 0)}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Live ETH</div>
              <div className="text-white text-xl font-bold">{formatEth(data.total_eth || 0)}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Tokens</div>
              <div className="text-[#00F0FF] text-xl font-bold">{data.tokens_owned || 0}</div>
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Claims</div>
              <div className="text-[#FFE600] text-xl font-bold">{data.claim_count}</div>
            </div>
          </div>
        </div>
        {data.tokens_claimed && data.tokens_claimed.length > 0 && (
          <div className="mt-4 pt-4 border-t border-[#00FF66]/10">
            <div className="text-[10px] tracking-widest text-[#52525B] uppercase mb-2">Tokens Owned</div>
            <div className="flex flex-wrap gap-2">
              {data.tokens_claimed.map((s) => (
                <span key={s} className="px-2 py-1 border border-[#00F0FF]/40 text-[#00F0FF] text-xs font-mono">
                  ${s}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {data.tokens && data.tokens.length > 0 && (
        <div className="panel corners">
          <div className="p-4 border-b border-[#00FF66]/20 text-head text-sm tracking-[0.2em] uppercase">
            Owned Tokens
          </div>
          <div className="divide-y divide-[#00FF66]/10">
            {data.tokens.map((t) => (
              <Link
                key={t.address}
                to={`/tokens/${t.address}`}
                className="flex items-center gap-4 p-3 hover:bg-[#00FF66]/5"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[#00F0FF] font-semibold">${t.symbol}</div>
                  <div className="text-[10px] text-[#52525B] truncate">{t.name}</div>
                </div>
                <div className="text-right">
                  <div className="text-[#00FF66] font-semibold">{formatEth(t.lifetime_earned_weth || t.total_claimed_eth || 0)} Ξ</div>
                  <div className="text-[10px] text-[#52525B]">{t.total_claim_count || 0} claims</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {data.claims && data.claims.length > 0 && (
        <div className="panel corners">
          <div className="p-4 border-b border-[#00FF66]/20 text-head text-sm tracking-[0.2em] uppercase">
            Live Claim History
          </div>
          <div className="divide-y divide-[#00FF66]/10">
            {data.claims.map((c) => (
              <div key={c.id} className="flex items-center gap-4 p-3 hover:bg-[#00FF66]/5">
                <Link to={`/tokens/${c.token_address}`} className="flex-1 min-w-0">
                  <div className="text-[#00F0FF] font-semibold">${c.token_symbol}</div>
                  <div className="text-[10px] text-[#52525B] truncate">{c.token_name}</div>
                </Link>
                <div className="text-right">
                  <div className="text-[#00FF66] font-semibold">{formatEth(c.amount_eth)} Ξ</div>
                  <div className="text-[10px] text-[#52525B]">{formatUsd(c.amount_usd)}</div>
                </div>
                <div className="text-right text-xs text-[#8A8A93] w-20">{timeAgo(c.timestamp)} ago</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
