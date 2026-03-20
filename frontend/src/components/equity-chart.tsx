"use client";

import { useEffect, useRef } from "react";
import { ColorType, createChart } from "lightweight-charts";

import { toEquitySeries } from "@/lib/chart";
import type { EquityPoint } from "@/lib/types";

type EquityChartProps = {
  points: EquityPoint[];
  comparePoints?: EquityPoint[];
  compareLabel?: string;
};

export function EquityChart({ points, comparePoints, compareLabel }: EquityChartProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current || points.length === 0) {
      return undefined;
    }

    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#17201d" },
        textColor: "#dbe6df"
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.06)" },
        horzLines: { color: "rgba(255,255,255,0.06)" }
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.1)"
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.1)"
      }
    });

    const primary = chart.addAreaSeries({
      lineColor: "#b8ff67",
      topColor: "rgba(184, 255, 103, 0.35)",
      bottomColor: "rgba(184, 255, 103, 0.04)"
    });

    primary.setData(toEquitySeries(points));

    if (comparePoints?.length) {
      const secondary = chart.addLineSeries({
        color: "#f3c96b",
        lineWidth: 2,
        title: compareLabel
      });
      secondary.setData(toEquitySeries(comparePoints));
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [compareLabel, comparePoints, points]);

  return <div ref={ref} className="h-[260px] w-full" />;
}
