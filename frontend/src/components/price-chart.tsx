"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  type IChartApi,
  LineStyle,
  type UTCTimestamp,
  createChart
} from "lightweight-charts";
import { toEquitySeries, toIndicatorSeries } from "@/lib/chart";
import type { Candle, EquityPoint, IndicatorSeriesPoint, Trade } from "@/lib/types";
import { SectionHeader, Surface } from "@/components/ui";

export type PriceChartOverlay = {
  id: string;
  label: string;
  color: string;
  data: IndicatorSeriesPoint[];
  lineWidth?: 1 | 2 | 3 | 4;
  lineStyle?: LineStyle;
};

type PriceChartProps = {
  candles: Candle[];
  trades?: Trade[];
  equity?: EquityPoint[];
  overlays?: PriceChartOverlay[];
  title: string;
  mode?: "candles" | "equity";
  shell?: boolean;
};

export function PriceChart({
  candles,
  trades = [],
  equity = [],
  overlays = [],
  title,
  mode = "candles",
  shell = true
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
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#5b6472"
      },
      grid: {
        vertLines: { color: "#eef2f6" },
        horzLines: { color: "#eef2f6" }
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#e3e8ef" },
      timeScale: { borderColor: "#e3e8ef" }
    });
    chartRef.current = chart;

    if (mode === "candles") {
      const series = chart.addCandlestickSeries({
        upColor: "#1f8f5f",
        downColor: "#c4554a",
        borderVisible: false,
        wickUpColor: "#1f8f5f",
        wickDownColor: "#c4554a"
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
            color: trade.side === "BUY" ? "#1f8f5f" : "#c4554a",
            shape: trade.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
            text: trade.side
          }))
          .sort((a, b) => (a.time as number) - (b.time as number))
      );

      overlays.forEach((overlay) => {
        if (overlay.data.length === 0) {
          return;
        }

        const overlaySeries = chart.addLineSeries({
          color: overlay.color,
          lineWidth: overlay.lineWidth ?? 2,
          lineStyle: overlay.lineStyle ?? LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false
        });
        overlaySeries.setData(toIndicatorSeries(overlay.data));
      });
    } else {
      const series = chart.addAreaSeries({
        lineColor: "#3e63dd",
        topColor: "rgba(62, 99, 221, 0.18)",
        bottomColor: "rgba(62, 99, 221, 0.02)"
      });
      series.setData(toEquitySeries(equity));
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, equity, trades, overlays, mode]);

  const content = (
    <>
      <SectionHeader compact title={title} />
      <div className="px-5 py-5">
        {mode === "candles" && overlays.length > 0 ? (
          <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500">
            {overlays.map((overlay) => (
              <span key={overlay.id} className="inline-flex items-center gap-1.5 rounded bg-slate-50 px-2 py-1">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: overlay.color }}
                  aria-hidden="true"
                />
                {overlay.label}
              </span>
            ))}
          </div>
        ) : null}
        <div ref={containerRef} className="h-[320px] w-full" />
      </div>
    </>
  );

  if (!shell) {
    return <section className="space-y-0">{content}</section>;
  }

  return <Surface className="overflow-hidden">{content}</Surface>;
}
