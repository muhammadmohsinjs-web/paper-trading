"use client";

import { useEffect, useRef, useState } from "react";
import { formatCurrency } from "@/lib/format";

type LivePriceProps = {
  price: number | null;
  variant?: "hero" | "inline";
  className?: string;
};

const PRICE_PULSE_MS = 560;

type PriceDirection = "up" | "down" | "idle";

export function LivePrice({
  price,
  variant = "hero",
  className = ""
}: LivePriceProps) {
  const previousPriceRef = useRef<number | null>(price);
  const resetDirectionTimeoutRef = useRef<number | null>(null);
  const [direction, setDirection] = useState<PriceDirection>("idle");
  const [pulseKey, setPulseKey] = useState(0);

  useEffect(() => {
    if (resetDirectionTimeoutRef.current !== null) {
      window.clearTimeout(resetDirectionTimeoutRef.current);
      resetDirectionTimeoutRef.current = null;
    }

    const previousPrice = previousPriceRef.current;

    if (price === null) {
      previousPriceRef.current = price;
      setDirection("idle");
      return;
    }

    if (previousPrice === null) {
      previousPriceRef.current = price;
      return;
    }

    if (price === previousPrice) {
      return;
    }

    setDirection(price > previousPrice ? "up" : "down");
    setPulseKey((current) => current + 1);
    previousPriceRef.current = price;
    resetDirectionTimeoutRef.current = window.setTimeout(() => {
      setDirection("idle");
      resetDirectionTimeoutRef.current = null;
    }, PRICE_PULSE_MS);
  }, [price]);

  useEffect(() => {
    return () => {
      if (resetDirectionTimeoutRef.current !== null) {
        window.clearTimeout(resetDirectionTimeoutRef.current);
      }
    };
  }, []);

  const variantClass =
    variant === "hero"
      ? "text-4xl font-semibold tracking-tight sm:text-5xl"
      : "text-sm font-medium";

  const directionClass =
    direction === "up"
      ? "price-value-up"
      : direction === "down"
        ? "price-value-down"
        : "";

  const pulseClass =
    direction === "up"
      ? "price-pulse-up"
      : direction === "down"
        ? "price-pulse-down"
        : "";

  return (
    <span className={`price-tick ${variantClass} ${className}`.trim()}>
      <span
        key={pulseKey}
        className={`price-value ${directionClass} ${pulseClass}`.trim()}
      >
        {formatCurrency(price)}
      </span>
    </span>
  );
}
