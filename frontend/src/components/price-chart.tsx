"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  type IChartApi,
  type UTCTimestamp,
  createChart
} from "lightweight-charts";
import { toEquitySeries } from "@/lib/chart";
import type { Candle, EquityPoint, Trade } from "@/lib/types";

type PriceChartProps = {
  candles: Candle[];
  trades?: Trade[];
  equity?: EquityPoint[];
  title: string;
  mode?: "candles" | "equity";
};

export function PriceChart({
  candles,
  trades = [],
  equity = [],
  title,
  mode = "candles"
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#101722" },
        textColor: "#dbe6df"
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" }
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)" }
    });
    chartRef.current = chart;

    if (mode === "candles") {
      const series = chart.addCandlestickSeries({
        upColor: "#b8ff67",
        downColor: "#ff7b5a",
        borderVisible: false,
        wickUpColor: "#b8ff67",
        wickDownColor: "#ff7b5a"
      });
      series.setData(
        candles.map((candle) => ({
          time: Math.floor(candle.open_time / 1000) as UTCTimestamp,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close
        }))
      );
      series.setMarkers(
        trades
          .map((trade) => ({
            time: Math.floor(new Date(trade.executed_at).getTime() / 1000) as UTCTimestamp,
            position: trade.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
            color: trade.side === "BUY" ? "#b8ff67" : "#ff7b5a",
            shape: trade.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
            text: trade.side
          }))
          .sort((a, b) => (a.time as number) - (b.time as number))
      );
    } else {
      const series = chart.addAreaSeries({
        lineColor: "#f3c96b",
        topColor: "rgba(243, 201, 107, 0.28)",
        bottomColor: "rgba(243, 201, 107, 0.02)"
      });
      series.setData(toEquitySeries(equity));
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, equity, trades, mode]);

  return (
    <div className="panel p-5">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.22em] text-mist/45">
          {mode === "equity" ? "Performance Curve" : "Market View"}
        </p>
        <h3 className="mt-2 text-xl font-semibold text-sand">{title}</h3>
      </div>
      <div ref={containerRef} className="h-[320px] w-full" />
    </div>
  );
}
