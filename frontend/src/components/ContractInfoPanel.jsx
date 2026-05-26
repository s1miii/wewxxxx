import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { getStats } from "@/lib/api";

const FEE_CONTRACT_TOPIC = "0x951cb665…289276d1";

export default function ContractInfoPanel() {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const s = await getStats();
        setInfo(s);
      } catch (e) {
        // ignore
      }
    };
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="panel corners scanline p-4" data-testid="contract-info-panel">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 border border-[#FFE600] text-[#FFE600] flex items-center justify-center">
            <Activity size={14} strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-head text-sm tracking-[0.2em] uppercase text-white">
              Indexing `Released` Events
            </div>
            <div className="text-xs font-mono text-[#00FF66]">
              topic <span className="text-[#FFE600]">{FEE_CONTRACT_TOPIC}</span>
            </div>
            <div className="text-[10px] text-[#52525B] mt-1 tracking-widest uppercase">
              Doppler · Streamable Fees Locker · Base
            </div>
          </div>
        </div>
        <div className="flex items-center gap-6 text-xs">
          <div className="text-right">
            <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Launches Indexed</div>
            <div className="text-[#00F0FF] font-mono" data-testid="indexer-last-block">
              {info?.bankr_launches_indexed?.toLocaleString() ?? "—"}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] tracking-widest text-[#52525B] uppercase">Tracked</div>
            <div className="text-[#FFE600] font-mono">{info?.tracked_tokens ?? "—"}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] tracking-widest text-[#52525B] uppercase">X Resolved</div>
            <div className="text-[#FF007A] font-mono">{info?.unique_handles ?? "—"}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
