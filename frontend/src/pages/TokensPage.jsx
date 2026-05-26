import TokensTable from "@/components/TokensTable";

export default function TokensPage() {
  return (
    <div className="space-y-6" data-testid="tokens-page">
      <div>
        <div className="text-[10px] tracking-[0.3em] text-[#00F0FF] uppercase mb-2">
          // CATALOG · AUTO-DISCOVERED
        </div>
        <h1 className="text-head text-3xl font-bold tracking-tighter">
          Indexed <span className="text-[#00F0FF] glow-cyan">Tokens</span>
        </h1>
        <p className="text-sm text-[#8A8A93] mt-1">
          Tokens auto-discovered from on-chain claim transfers leaving the
          Bankr/Doppler fee locker. Symbol + name resolved via ERC20 calls; X
          handle resolved via Bankr public API.
        </p>
      </div>
      <TokensTable />
    </div>
  );
}
