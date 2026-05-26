import { useEffect, useState } from "react";
import KPIStrip from "@/components/KPIStrip";
import LiveFeed from "@/components/LiveFeed";
import LifetimeLeaderboard from "@/components/LifetimeLeaderboard";
import ContractInfoPanel from "@/components/ContractInfoPanel";
import { getStats } from "@/lib/api";

export default function Dashboard({ onStatsUpdate }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const s = await getStats();
        setStats(s);
        onStatsUpdate?.(s);
      } catch (e) {
        // ignore
      }
    };
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Hero strip */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="text-[10px] tracking-[0.3em] text-[#00FF66] uppercase mb-2">
            // INDEXING `Released` EVENT · TOPIC 0x951cb665…
          </div>
          <h1 className="text-head text-4xl sm:text-5xl font-bold tracking-tighter">
            Bankr Bot <span className="text-[#00FF66] glow-green">Claim</span> Monitor
          </h1>
          <p className="text-sm text-[#8A8A93] mt-2 max-w-2xl">
            Real on-chain detection of every <span className="text-[#FFE600]">Bankr / Doppler</span>{" "}
            fee claim on Base. For each claim we extract token name + contract + market cap +
            liquidity from <span className="text-[#00F0FF]">DexScreener</span> and resolve the
            beneficiary's <span className="text-[#00F0FF]">@x.com handle</span> via Bankr's API.
          </p>
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest font-mono">
          <span className="blink">LIVE</span> · base · uniswap v4 · doppler
        </div>
      </div>

      <KPIStrip stats={stats} />

      <ContractInfoPanel />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <LiveFeed />
        </div>
        <div>
          <LifetimeLeaderboard limit={12} />
        </div>
      </div>
    </div>
  );
}
