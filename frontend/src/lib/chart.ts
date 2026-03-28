import type { UTCTimestamp } from "lightweight-charts";

import type { EquityPoint, IndicatorSeriesPoint } from "@/lib/types";

export type ChartValuePoint = {
  time: UTCTimestamp;
  value: number;
};

export function toEquitySeries(points: EquityPoint[]): ChartValuePoint[] {
  const dedupedBySecond = new Map<number, number>();

  for (const point of points) {
    const timestamp = new Date(point.timestamp).getTime();
    if (Number.isNaN(timestamp)) {
      continue;
    }

    dedupedBySecond.set(Math.floor(timestamp / 1000), point.total_equity_usdt);
  }

  return Array.from(dedupedBySecond.entries())
    .sort(([left], [right]) => left - right)
    .map(([time, value]) => ({
      time: time as UTCTimestamp,
      value
    }));
}

export function toIndicatorSeries(points: IndicatorSeriesPoint[]): ChartValuePoint[] {
  const dedupedBySecond = new Map<number, number>();

  for (const point of points) {
    const time = Math.floor(point.open_time / 1000);
    if (!Number.isFinite(time)) {
      continue;
    }

    dedupedBySecond.set(time, point.value);
  }

  return Array.from(dedupedBySecond.entries())
    .sort(([left], [right]) => left - right)
    .map(([time, value]) => ({
      time: time as UTCTimestamp,
      value
    }));
}
