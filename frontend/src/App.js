import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Header from "@/components/Header";
import Dashboard from "@/pages/Dashboard";
import TokenDetail from "@/pages/TokenDetail";
import ClaimerDetail from "@/pages/ClaimerDetail";
import WalletDetail from "@/pages/WalletDetail";
import LeaderboardPage from "@/pages/LeaderboardPage";
import TokensPage from "@/pages/TokensPage";
import { getStats } from "@/lib/api";

function App() {
  const [ethPrice, setEthPrice] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const s = await getStats();
        setEthPrice(s.eth_price_usd);
      } catch (e) {
        // ignore
      }
    };
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="App min-h-screen text-white" data-testid="app-root">
      <BrowserRouter>
        <Header ethPrice={ethPrice} />
        <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard onStatsUpdate={(s) => setEthPrice(s.eth_price_usd)} />} />
            <Route path="/tokens" element={<TokensPage />} />
            <Route path="/tokens/:address" element={<TokenDetail />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/handle/:handle" element={<ClaimerDetail />} />
            <Route path="/wallet/:address" element={<WalletDetail />} />
          </Routes>
        </main>
        <footer className="border-t border-[#00FF66]/15 mt-12 py-6 text-center text-[10px] tracking-[0.3em] text-[#52525B] uppercase">
          BANKR.SCAN · INDEXING 0xD59cE43E…91178 ON BASE · ERC20 + BANKR API
        </footer>
      </BrowserRouter>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#0F0F13",
            border: "1px solid rgba(0, 255, 102, 0.4)",
            borderRadius: 0,
            color: "#fff",
            fontFamily: "IBM Plex Mono",
          },
        }}
      />
    </div>
  );
}

export default App;
