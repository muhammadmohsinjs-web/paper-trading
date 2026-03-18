"use client";

import { useEffect, useRef, useState } from "react";

import type { LiveEvent } from "@/lib/types";

type UseWebSocketOptions = {
  enabled?: boolean;
};

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const { enabled = true } = options;
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [eventCount, setEventCount] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      socket.send("ping");
    };

    socket.onclose = () => {
      setIsConnected(false);
    };

    socket.onerror = () => {
      setIsConnected(false);
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as LiveEvent;
        setLastEvent(payload);
        setEventCount((current) => current + 1);
      } catch {
        setLastEvent({ type: "unparsed", raw: event.data });
        setEventCount((current) => current + 1);
      }
    };

    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 15000);

    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, [enabled, url]);

  return {
    isConnected,
    lastEvent,
    eventCount
  };
}
