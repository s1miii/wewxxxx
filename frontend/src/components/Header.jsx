import { Link, useLocation } from "react-router-dom";
import { Activity, Search } from "lucide-react";
import { useEffect, useState } from "react";

export default function Header({ ethPrice }) {
  const location = useLocation();
  const [clock, setClock] = useState("");

  useEffect(() => {
    const t = () => {
      const d = new Date();
      setClock(
        `${d.toUTCString().split(" ")[4]} UTC`
      );
    };
    t();
    const id = setInterval(t, 1000);
    return () => clearInterval(id);
  }, []);

  const isActive = (p) => location.pathname === p;

  return (
    <header
      className="sticky top-0 z-50 backdrop-blur-xl bg-[#050505]/85 border-b border-[#00FF66]/20"
      data-testid="app-header"
    >
      <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between gap-6">
        <Link to="/" className="flex items-center gap-3 group" data-testid="logo-link">
          <div className="relative">
            <div className="w-9 h-9 border border-[#00FF66] flex items-center justify-center text-[#00FF66] glow-green">
              <Activity size={18} strokeWidth={2.5} />
            </div>
            <div className="absolute -top-1 -right-1 w-2 h-2 bg-[#00FF66] pulse-dot rounded-full"></div>
          </div>
          <div className="leading-none">
            <div className="text-head text-lg font-bold tracking-tighter">
              BANKR<span className="text-[#00FF66]">.</span>SCAN
            </div>
            <div className="text-[10px] text-[#8A8A93] tracking-[0.2em] uppercase mt-1">
              FEE CLAIM MONITOR // BASE
            </div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1" data-testid="main-nav">
          {[
            { to: "/", label: "FEED" },
            { to: "/leaderboard", label: "LEADERBOARD" },
            { to: "/tokens", label: "TOKENS" },
          ].map((n) => (
            <Link
              key={n.to}
              to={n.to}
              data-testid={`nav-${n.label.toLowerCase()}`}
              className={`px-4 py-2 text-xs tracking-[0.2em] border ${
                isActive(n.to)
                  ? "border-[#00FF66] text-[#00FF66] glow-green bg-[#00FF66]/5"
                  : "border-transparent text-[#8A8A93] hover:text-white hover:border-[#00FF66]/40"
              } transition-all`}
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-4 text-xs text-[#8A8A93]" data-testid="header-status">
          <div className="hidden sm:flex items-center gap-2">
            <div className="w-1.5 h-1.5 bg-[#00FF66] pulse-dot rounded-full"></div>
            <span className="tracking-widest">LIVE</span>
          </div>
          <div className="hidden md:block text-[#FFE600]" data-testid="eth-price">
            ETH ${ethPrice ? Number(ethPrice).toLocaleString() : "—"}
          </div>
          <div className="hidden lg:block text-[#52525B]">{clock}</div>
        </div>
      </div>
    </header>
  );
}
