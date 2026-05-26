import { TrendingUp, Coins, Users, Zap } from "lucide-react";
import { formatEth, formatUsd } from "@/lib/api";

function KPI({ label, value, sub, icon: Icon, accent, testid }) {
  return (
    <div
      className="panel panel-hover corners p-5 flex flex-col justify-between min-h-[120px] relative overflow-hidden"
      data-testid={testid}
    >
      <div className="flex items-start justify-between">
        <div className="text-[10px] tracking-[0.2em] text-[#8A8A93] uppercase">
          {label}
        </div>
        <Icon size={16} className={accent} />
      </div>
      <div>
        <div className={`text-head text-3xl font-bold ${accent} tracking-tight`}>
          {value}
        </div>
        {sub && (
          <div className="text-xs text-[#52525B] mt-1 tracking-wide">{sub}</div>
        )}
      </div>
    </div>
  );
}

export default function KPIStrip({ stats }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="kpi-strip-loading">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="panel p-5 min-h-[120px] animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="kpi-strip">
      <KPI
        label="Lifetime Claims"
        value={(stats.lifetime_claim_count || 0).toLocaleString()}
        sub={`${stats.total_claims} since monitor start`}
        icon={Zap}
        accent="text-[#00FF66] glow-green"
        testid="kpi-total-claims"
      />
      <KPI
        label="Lifetime ETH"
        value={`${formatEth(stats.lifetime_eth || 0)} Ξ`}
        sub={formatUsd(stats.lifetime_usd || 0)}
        icon={Coins}
        accent="text-[#00F0FF] glow-cyan"
        testid="kpi-total-eth"
      />
      <KPI
        label="X Creators"
        value={stats.unique_handles || 0}
        sub={`${stats.bankr_launches_indexed} launches indexed`}
        icon={Users}
        accent="text-[#FFE600]"
        testid="kpi-unique-claimers"
      />
      <KPI
        label="Live 24h Claims"
        value={`${formatEth(stats.eth_24h)} Ξ`}
        sub={`${stats.claims_24h} new claims · ${formatUsd(stats.usd_24h)}`}
        icon={TrendingUp}
        accent="text-[#FF007A] glow-pink"
        testid="kpi-24h-volume"
      />
    </div>
  );
}
