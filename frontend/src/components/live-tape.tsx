"use client";

import { useMemo } from "react";

import { useWebSocket } from "@/hooks/use-websocket";
import { wsBaseUrl } from "@/lib/env";
import { formatDateTime } from "@/lib/format";
import { StatusPill } from "@/components/status-pill";

export function LiveTape() {
  const { isConnected, lastEvent, eventCount } = useWebSocket(`${wsBaseUrl}/ws/live`);
  const summary = useMemo(() => {
    if (!lastEvent) {
      return "Waiting for live broadcasts from backend.";
    }
    const type = typeof lastEvent.type === "string" ? lastEvent.type : "event";
    return `${type} ${JSON.stringify(lastEvent).slice(0, 120)}`;
  }, [lastEvent]);

  return (
    <div className="rounded-[28px] border border-white/10 bg-panel/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Live Feed</div>
          <div className="mt-2 text-xl font-semibold text-sand">WebSocket monitor</div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill tone={isConnected ? "rise" : "fall"}>
            {isConnected ? "Connected" : "Disconnected"}
          </StatusPill>
          <StatusPill tone="muted">{eventCount} events</StatusPill>
        </div>
      </div>
      <div className="mt-4 rounded-[20px] border border-white/8 bg-black/20 p-4 text-sm text-mist/70">
        <div>{summary}</div>
        <div className="mt-2 text-xs text-mist/45">{formatDateTime(new Date().toISOString())}</div>
      </div>
    </div>
  );
}
