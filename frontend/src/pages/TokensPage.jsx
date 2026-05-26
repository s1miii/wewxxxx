import TokensTable from "@/components/TokensTable";
import AddTokenForm from "@/components/AddTokenForm";

export default function TokensPage() {
  return (
    <div className="space-y-6" data-testid="tokens-page">
      <div>
        <div className="text-[10px] tracking-[0.3em] text-[#00F0FF] uppercase mb-2">
          // CATALOG
        </div>
        <h1 className="text-head text-3xl font-bold tracking-tighter">
          Tracked <span className="text-[#00F0FF] glow-cyan">Tokens</span>
        </h1>
        <p className="text-sm text-[#8A8A93] mt-1">
          All Bankr-launched tokens being monitored. Click any token to see its
          claim history and per-day chart.
        </p>
      </div>
      <AddTokenForm />
      <TokensTable />
    </div>
  );
}
