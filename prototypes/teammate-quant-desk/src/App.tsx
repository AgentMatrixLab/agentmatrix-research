import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Home from "@/pages/Home";
import Portfolio from "@/pages/Portfolio";
import BacktestCenter from "@/pages/BacktestCenter";
import Positions from "@/pages/Positions";
import Trades from "@/pages/Trades";
import Risk from "@/pages/Risk";

export default function App() {
  return (
    <BrowserRouter basename="/quant-desk">
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/backtest" element={<BacktestCenter />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="*" element={<Home />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
