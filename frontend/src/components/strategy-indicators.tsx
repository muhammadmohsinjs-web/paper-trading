"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart
} from "lightweight-charts";
import { toIndicatorSeries } from "@/lib/chart";
import type { PriceChartOverlay } from "@/components/price-chart";
import { SectionHeader, StatusBadge, Surface } from "@/components/ui";
import type {
  IndicatorSeriesPoint,
  MarketIndicatorsResponse,
  StrategyType
} from "@/lib/types";

type IndicatorPanelSeriesDefinition = {
  id: string;
  label: string;
  color: string;
  data: IndicatorSeriesPoint[];
  type?: "line" | "histogram";
};

export type IndicatorPanelDefinition = {
  id: string;
  title: string;
  subtitle?: string;
  thresholds?: number[];
  series: IndicatorPanelSeriesDefinition[];
};

type StrategyIndicatorDisplay = {
  overlays: PriceChartOverlay[];
  panels: IndicatorPanelDefinition[];
  activeLabels: string[];
};

function pushOverlay(
  overlays: PriceChartOverlay[],
  activeLabels: string[],
  overlay: PriceChartOverlay
) {
  if (overlay.data.length === 0) {
    return;
  }

  overlays.push(overlay);
  activeLabels.push(overlay.label);
}

function pushPanel(
  panels: IndicatorPanelDefinition[],
  activeLabels: string[],
  panel: IndicatorPanelDefinition
) {
  if (!panel.series.some((series) => series.data.length > 0)) {
    return;
  }

  panels.push(panel);
  activeLabels.push(panel.title);
}

export function buildStrategyIndicatorDisplay(
  strategyType: StrategyType,
  indicators: MarketIndicatorsResponse
): StrategyIndicatorDisplay {
  const overlays: PriceChartOverlay[] = [];
  const panels: IndicatorPanelDefinition[] = [];
  const activeLabels: string[] = [];
  const { series } = indicators;
  const { sma_short, sma_long } = indicators.config;

  if (strategyType === "sma_crossover") {
    pushOverlay(overlays, activeLabels, {
      id: "sma-short",
      label: `SMA ${sma_short}`,
      color: "#2563eb",
      data: series.sma_short
    });
    pushOverlay(overlays, activeLabels, {
      id: "sma-long",
      label: `SMA ${sma_long}`,
      color: "#f59e0b",
      data: series.sma_long
    });
    pushPanel(panels, activeLabels, {
      id: "volume-ratio",
      title: "Volume Ratio",
      subtitle: "Confirms crossovers when volume expands above average.",
      thresholds: [1],
      series: [
        {
          id: "volume-ratio",
          label: "Volume Ratio",
          color: "#0f766e",
          data: series.volume_ratio
        }
      ]
    });
  }

  if (strategyType === "rsi_mean_reversion") {
    pushPanel(panels, activeLabels, {
      id: "rsi",
      title: "RSI",
      subtitle: "Mean-reversion watches oversold and overbought extremes.",
      thresholds: [30, 70],
      series: [
        {
          id: "rsi",
          label: "RSI",
          color: "#7c3aed",
          data: series.rsi
        }
      ]
    });
  }

  if (strategyType === "macd_momentum") {
    pushPanel(panels, activeLabels, {
      id: "macd",
      title: "MACD",
      subtitle: "Momentum entries follow MACD and signal-line crossovers.",
      thresholds: [0],
      series: [
        {
          id: "macd-histogram",
          label: "Histogram",
          color: "#cbd5e1",
          data: series.macd_histogram,
          type: "histogram"
        },
        {
          id: "macd-line",
          label: "MACD",
          color: "#f97316",
          data: series.macd_line
        },
        {
          id: "macd-signal",
          label: "Signal",
          color: "#2563eb",
          data: series.macd_signal
        }
      ]
    });
  }

  if (strategyType === "bollinger_bounce") {
    pushOverlay(overlays, activeLabels, {
      id: "bb-upper",
      label: "BB Upper",
      color: "#14b8a6",
      data: series.bollinger_upper
    });
    pushOverlay(overlays, activeLabels, {
      id: "bb-middle",
      label: "BB Middle",
      color: "#475569",
      data: series.bollinger_middle,
      lineStyle: LineStyle.Dashed
    });
    pushOverlay(overlays, activeLabels, {
      id: "bb-lower",
      label: "BB Lower",
      color: "#14b8a6",
      data: series.bollinger_lower
    });
  }

  if (strategyType === "hybrid_composite") {
    pushOverlay(overlays, activeLabels, {
      id: "ema-12",
      label: "EMA 12",
      color: "#2563eb",
      data: series.ema_12
    });
    pushOverlay(overlays, activeLabels, {
      id: "ema-26",
      label: "EMA 26",
      color: "#f97316",
      data: series.ema_26
    });
    pushOverlay(overlays, activeLabels, {
      id: "sma-short",
      label: `SMA ${sma_short}`,
      color: "#0f766e",
      data: series.sma_short
    });
    pushOverlay(overlays, activeLabels, {
      id: "sma-long",
      label: `SMA ${sma_long}`,
      color: "#a16207",
      data: series.sma_long
    });
    pushPanel(panels, activeLabels, {
      id: "hybrid-rsi",
      title: "RSI",
      subtitle: "One of the weighted votes in the hybrid composite score.",
      thresholds: [30, 70],
      series: [
        {
          id: "hybrid-rsi-line",
          label: "RSI",
          color: "#7c3aed",
          data: series.rsi
        }
      ]
    });
    pushPanel(panels, activeLabels, {
      id: "hybrid-macd",
      title: "MACD",
      subtitle: "Shows directional momentum used by the composite scorer.",
      thresholds: [0],
      series: [
        {
          id: "hybrid-macd-histogram",
          label: "Histogram",
          color: "#cbd5e1",
          data: series.macd_histogram,
          type: "histogram"
        },
        {
          id: "hybrid-macd-line",
          label: "MACD",
          color: "#f97316",
          data: series.macd_line
        },
        {
          id: "hybrid-macd-signal",
          label: "Signal",
          color: "#2563eb",
          data: series.macd_signal
        }
      ]
    });
    pushPanel(panels, activeLabels, {
      id: "hybrid-volume",
      title: "Volume Ratio",
      subtitle: "Volume dampening and conviction both depend on this series.",
      thresholds: [1],
      series: [
        {
          id: "hybrid-volume-ratio",
          label: "Volume Ratio",
          color: "#0f766e",
          data: series.volume_ratio
        }
      ]
    });
    pushPanel(panels, activeLabels, {
      id: "hybrid-adx",
      title: "ADX",
      subtitle: "Trend-strength context from the implemented indicator set.",
      thresholds: [25],
      series: [
        {
          id: "hybrid-adx-line",
          label: "ADX",
          color: "#dc2626",
          data: series.adx
        }
      ]
    });
  }

  return {
    overlays,
    panels,
    activeLabels: Array.from(new Set(activeLabels))
  };
}

function IndicatorPane({ panel }: { panel: IndicatorPanelDefinition }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

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

    let thresholdsApplied = false;

    panel.series.forEach((series) => {
      if (series.data.length === 0) {
        return;
      }

      const data = toIndicatorSeries(series.data);
      if (series.type === "histogram") {
        const histogramSeries = chart.addHistogramSeries({
          color: series.color,
          base: 0,
          priceLineVisible: false,
          lastValueVisible: false
        });
        histogramSeries.setData(data);
        return;
      }

      const lineSeries = chart.addLineSeries({
        color: series.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false
      });
      lineSeries.setData(data);

      if (!thresholdsApplied && panel.thresholds) {
        panel.thresholds.forEach((level) => {
          lineSeries.createPriceLine({
            price: level,
            color: "#cbd5e1",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: String(level)
          });
        });
        thresholdsApplied = true;
      }
    });

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [panel]);

  return (
    <Surface className="overflow-hidden">
      <div className="border-b border-slate-200 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">{panel.title}</h3>
          {panel.series.map((series) => (
            <span
              key={series.id}
              className="inline-flex items-center gap-1.5 rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-500"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: series.color }}
                aria-hidden="true"
              />
              {series.label}
            </span>
          ))}
        </div>
        {panel.subtitle ? (
          <p className="mt-1 text-xs leading-5 text-slate-500">{panel.subtitle}</p>
        ) : null}
      </div>
      <div className="px-5 py-4">
        <div ref={containerRef} className="h-[180px] w-full" />
      </div>
    </Surface>
  );
}

export function StrategyIndicatorPanels({
  panels,
  activeLabels
}: {
  panels: IndicatorPanelDefinition[];
  activeLabels: string[];
}) {
  if (panels.length === 0) {
    return null;
  }

  return (
    <section className="space-y-4">
      <SectionHeader
        title="Strategy Indicators"
        description="Rendered from the same indicator calculations the selected strategy uses."
      />
      <div className="flex flex-wrap gap-2 px-6">
        {activeLabels.map((label) => (
          <StatusBadge key={label}>{label}</StatusBadge>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {panels.map((panel) => (
          <IndicatorPane key={panel.id} panel={panel} />
        ))}
      </div>
    </section>
  );
}
