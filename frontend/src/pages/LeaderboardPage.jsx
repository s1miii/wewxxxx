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
          Twitter / x.com handles ranked by total ETH claimed from Bankr-launched tokens.
        </p>
      </div>
      <div className="max-w-3xl">
        <Leaderboard limit={25} />
      </div>
    </div>
  );
}
