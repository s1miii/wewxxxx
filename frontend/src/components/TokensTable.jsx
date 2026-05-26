import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getTokens, formatEth, formatUsd, shortAddress, timeAgo } from "@/lib/api";

export default function TokensTable() {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getTokens(100);
        setTokens(data.items);
      } finally {
        setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="panel corners" data-testid="tokens-table">
      <div className="flex items-center justify-between p-4 border-b border-[#00FF66]/20">
        <div className="text-head text-sm tracking-[0.2em] uppercase">
          Tracked Tokens
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest">{tokens.length} ASSETS</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] tracking-[0.2em] uppercase text-[#8A8A93] border-b border-[#00FF66]/20">
              <th className="text-left py-3 px-4">Token</th>
              <th className="text-left py-3 px-4">Creator</th>
              <th className="text-left py-3 px-4 hidden md:table-cell">Contract</th>
              <th className="text-right py-3 px-4">Lifetime ETH</th>
              <th className="text-right py-3 px-4 hidden lg:table-cell">USD</th>
              <th className="text-right py-3 px-4 hidden sm:table-cell">Claims</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="text-center py-12 text-[#52525B] text-xs">
                  <span className="blink">Loading tokens</span>
                </td>
              </tr>
            )}
            {tokens.map((t) => (
              <tr
                key={t.address}
                data-testid={`token-row-${t.symbol}`}
                className="border-b border-[#00FF66]/10 hover:bg-[#00FF66]/5 transition-colors"
              >
                <td className="py-3 px-4">
                  <Link to={`/tokens/${t.address}`} className="group" data-testid={`token-detail-link-${t.symbol}`}>
                    <div className="text-[#00F0FF] font-bold glow-cyan group-hover:underline">${t.symbol}</div>
                    <div className="text-[11px] text-[#52525B]">{t.name}</div>
                  </Link>
                </td>
                <td className="py-3 px-4">
                  {t.creator_handle ? (
                    <Link
                      to={`/handle/${t.creator_handle}`}
                      className="inline-flex items-center gap-2 group"
                    >
                      <img
                        src={t.creator_avatar}
                        alt={t.creator_handle}
                        className="w-6 h-6 border border-[#00FF66]/30"
                      />
                      <span className="text-white group-hover:text-[#00FF66] transition-colors text-xs">
                        @{t.creator_handle}
                      </span>
                    </Link>
                  ) : (
                    <span className="text-[#52525B] text-xs italic">— unresolved —</span>
                  )}
                </td>
                <td className="py-3 px-4 hidden md:table-cell">
                  <a
                    href={`https://basescan.org/token/${t.address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-[#8A8A93] hover:text-[#00FF66]"
                  >
                    {shortAddress(t.address)}
                  </a>
                </td>
                <td className="py-3 px-4 text-right text-[#00FF66] font-semibold">
                  {formatEth(t.lifetime_earned_weth || t.total_claimed_eth || 0)} Ξ
                </td>
                <td className="py-3 px-4 text-right text-xs text-white hidden lg:table-cell">
                  {formatUsd((t.lifetime_earned_weth || t.total_claimed_eth || 0) * 1)}
                </td>
                <td className="py-3 px-4 text-right text-xs text-[#FFE600] hidden sm:table-cell">
                  {t.total_claim_count || 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
