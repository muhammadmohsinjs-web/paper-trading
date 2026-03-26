import { notFound } from "next/navigation";
import { StrategyDetailClient } from "@/components/strategy-detail-client";
import {
  getCandles,
  getEquityCurve,
  getPositions,
  getStrategy,
  getTradeSummary,
  getTrades
} from "@/lib/api";

type StrategyDetailPageProps = {
  params: { id: string };
};

export default async function StrategyDetailPage({ params }: StrategyDetailPageProps) {
  try {
    const strategy = await getStrategy(params.id);
    const chartSymbol = strategy.focus_symbol || strategy.primary_symbol || "BTCUSDT";
    const [positions, trades, summary, equity, candleResponse] = await Promise.all([
      getPositions(params.id),
      getTrades(params.id, 80),
      getTradeSummary(params.id),
      getEquityCurve(params.id, 160),
      getCandles(chartSymbol, "5m", 160)
    ]);

    return (
      <StrategyDetailClient
        strategy={strategy}
        positions={positions}
        trades={trades}
        summary={summary}
        equity={equity}
        candles={candleResponse.candles}
        chartSymbol={chartSymbol}
      />
    );
  } catch {
    notFound();
  }
}
