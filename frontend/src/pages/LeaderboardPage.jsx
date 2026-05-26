import LifetimeLeaderboard from "@/components/LifetimeLeaderboard";
import Leaderboard from "@/components/Leaderboard";

export default function LeaderboardPage() {
  return (
    <div className="space-y-6" data-testid="leaderboard-page">
      <div>
        <div className="text-[10px] tracking-[0.3em] text-[#FFE600] uppercase mb-2">
          // RANKINGS
        </div>
        <h1 className="text-head text-3xl font-bold tracking-tighter">
          Top Fee <span className="text-[#FFE600] glow-cyan">Claimers</span>
        </h1>
        <p className="text-sm text-[#8A8A93] mt-1">
          Twitter / x.com handles ranked by ETH claimed from Bankr-launched
          tokens on Base. Lifetime totals come from Bankr's public API; live
          totals are what we've observed since this monitor started.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <LifetimeLeaderboard limit={25} />
        <Leaderboard limit={25} />
      </div>
    </div>
  );
}
