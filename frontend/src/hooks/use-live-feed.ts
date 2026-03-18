"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { wsBaseUrl } from "@/lib/env";
import type { LiveEvent } from "@/lib/types";

type FeedState = {
  connected: boolean;
  latestPriceBySymbol: Record<string, number>;
  lastTradeEvent: LiveEvent | null;
  lastPositionEvent: LiveEvent | null;
};

export function useLiveFeed() {
  const [state, setState] = useState<FeedState>({
    connected: false,
    latestPriceBySymbol: {},
    lastTradeEvent: null,
    lastPositionEvent: null
  });
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number | null>(null);
  const keepAliveRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const cleanup = () => {
      if (retryRef.current) {
        window.clearTimeout(retryRef.current);
        retryRef.current = null;
      }
      if (keepAliveRef.current) {
        window.clearInterval(keepAliveRef.current);
        keepAliveRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };

    const connect = () => {
      cleanup();
      const socket = new WebSocket(`${wsBaseUrl}/ws/live`);
      socketRef.current = socket;

      socket.addEventListener("open", () => {
        if (cancelled) {
          return;
        }
        if (retryRef.current) {
          window.clearTimeout(retryRef.current);
          retryRef.current = null;
        }
        setState((current) => ({ ...current, connected: true }));
        keepAliveRef.current = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send("ping");
          }
        }, 15_000);
      });

      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data) as LiveEvent;
        setState((current) => {
          if (payload.type === "price_update" && payload.symbol && typeof payload.price === "number") {
            return {
              ...current,
              latestPriceBySymbol: {
                ...current.latestPriceBySymbol,
                [payload.symbol]: payload.price
              }
            };
          }
          if (payload.type === "trade_executed") {
            return { ...current, lastTradeEvent: payload };
          }
          if (payload.type === "position_changed") {
            return { ...current, lastPositionEvent: payload };
          }
          return current;
        });
      });

      const scheduleReconnect = () => {
        if (cancelled || socketRef.current !== socket || retryRef.current) {
          return;
        }
        setState((current) => ({ ...current, connected: false }));
        retryRef.current = window.setTimeout(() => {
          retryRef.current = null;
          connect();
        }, 3_000);
      };

      socket.addEventListener("error", () => {
        if (cancelled || socketRef.current !== socket) {
          return;
        }
        setState((current) => ({ ...current, connected: false }));
      });
      socket.addEventListener("close", scheduleReconnect);
    };

    connect();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, []);

  return useMemo(() => state, [state]);
}
