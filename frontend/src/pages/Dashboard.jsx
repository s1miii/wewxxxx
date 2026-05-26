import { useEffect, useState } from "react";
import KPIStrip from "@/components/KPIStrip";
import LiveFeed from "@/components/LiveFeed";
import Leaderboard from "@/components/Leaderboard";
import AddTokenForm from "@/components/AddTokenForm";
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
            // SYSTEM ONLINE
          </div>
          <h1 className="text-head text-4xl sm:text-5xl font-bold tracking-tighter">
            Bankr Bot <span className="text-[#00FF66] glow-green">Claim</span> Monitor
          </h1>
          <p className="text-sm text-[#8A8A93] mt-2 max-w-2xl">
            Real-time stream of trading fee claims from Bankr-launched tokens on Base.
            Watch which <span className="text-[#00F0FF]">x.com handles</span> are pulling fees from the flywheel.
          </p>
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest font-mono">
          <span className="blink">RPC</span> · base · uniswap.v4
        </div>
      </div>

      <KPIStrip stats={stats} />

      <AddTokenForm />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <LiveFeed />
        </div>
        <div>
          <Leaderboard limit={10} />
        </div>
      </div>
    </div>
  );
}
