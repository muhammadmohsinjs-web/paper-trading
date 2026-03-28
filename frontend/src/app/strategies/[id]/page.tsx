import { notFound } from "next/navigation";
import { StrategyDetailClient } from "@/components/strategy-detail-client";
import {
  getCandles,
  getEquityCurve,
  getIndicatorSeries,
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
    const chartInterval = strategy.candle_interval || "1h";
    const rawConfig = strategy.config_json ?? {};
    const indicatorConfig = {
      sma_short: typeof rawConfig.sma_short === "number" ? rawConfig.sma_short : undefined,
      sma_long: typeof rawConfig.sma_long === "number" ? rawConfig.sma_long : undefined,
      rsi_period: typeof rawConfig.rsi_period === "number" ? rawConfig.rsi_period : undefined,
      volume_ma_period:
        typeof rawConfig.volume_ma_period === "number" ? rawConfig.volume_ma_period : undefined
    };
    const chartLimit = Math.max(
      160,
      (indicatorConfig.sma_long ?? 50) + 60,
      (indicatorConfig.volume_ma_period ?? 20) + 60,
      (indicatorConfig.rsi_period ?? 14) + 60
    );

    const [positions, trades, summary, equity, candleResponse, indicators] = await Promise.all([
      getPositions(params.id),
      getTrades(params.id, 80),
      getTradeSummary(params.id),
      getEquityCurve(params.id, 160),
      getCandles(chartSymbol, chartInterval, chartLimit),
      getIndicatorSeries(chartSymbol, chartInterval, chartLimit, indicatorConfig)
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
        chartInterval={chartInterval}
        indicators={indicators}
      />
    );
  } catch {
    notFound();
  }
}
