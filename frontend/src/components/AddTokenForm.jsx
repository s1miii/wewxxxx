import { useState } from "react";
import { Plus, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { trackToken } from "@/lib/api";
import { toast } from "sonner";

export default function AddTokenForm({ onAdded }) {
  const [address, setAddress] = useState("");
  const [handle, setHandle] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!address) return;
    setBusy(true);
    try {
      const res = await trackToken({
        address: address.trim(),
        creator_handle: handle.trim() || undefined,
      });
      if (res.status === "exists") {
        toast.info(`Already tracking $${res.token.symbol}`);
      } else {
        toast.success(`Now tracking $${res.token.symbol} by @${res.token.creator_handle}`);
        setAddress("");
        setHandle("");
        onAdded?.(res.token);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to add token");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="panel corners p-4 flex flex-col gap-3"
      data-testid="add-token-form"
    >
      <div className="flex items-center justify-between">
        <div className="text-head text-sm tracking-[0.2em] uppercase text-white">
          Track Token
        </div>
        <div className="text-[10px] text-[#52525B] tracking-widest">BASE · 0x...</div>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          data-testid="add-token-address"
          required
          placeholder="0xTokenAddressOnBase..."
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          className="flex-1 rounded-none bg-[#050505] border-[#00FF66]/30 text-sm font-mono focus-visible:border-[#00FF66] focus-visible:ring-0 placeholder:text-[#52525B]"
        />
        <Input
          data-testid="add-token-handle"
          placeholder="@creator (optional)"
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          className="sm:w-48 rounded-none bg-[#050505] border-[#00FF66]/30 text-sm font-mono focus-visible:border-[#00FF66] focus-visible:ring-0 placeholder:text-[#52525B]"
        />
        <Button
          type="submit"
          data-testid="add-token-submit"
          disabled={busy}
          className="rounded-none bg-[#00FF66] text-black font-bold uppercase tracking-wider hover:bg-[#00FF66]/80 hover:shadow-[0_0_18px_rgba(0,255,102,0.5)] transition-all border-0"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          <span className="ml-1">TRACK</span>
        </Button>
      </div>
      <div className="text-[10px] text-[#52525B] tracking-wide leading-relaxed">
        Resolves token metadata via Bankr public API (api.bankr.bot/token-launches/&lt;addr&gt;/fees).
        Once tracked, fee claims will appear in the live stream.
      </div>
    </form>
  );
}
