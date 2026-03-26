"use client";

import { useEffect, useState } from "react";
import { formatDateTime } from "@/lib/format";

type LocalDateTimeProps = {
  value: string | null | undefined;
  className?: string;
  options?: Intl.DateTimeFormatOptions;
};

export function LocalDateTime({ value, className, options }: LocalDateTimeProps) {
  const [timeZone, setTimeZone] = useState<string | null>(null);
  const date = value ? new Date(value) : null;
  const isValidDate = Boolean(date && !Number.isNaN(date.getTime()));
  const label = formatDateTime(value, {
    ...options,
    timeZone: timeZone ?? "UTC"
  });

  useEffect(() => {
    setTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  }, []);

  return (
    <time
      className={className}
      dateTime={isValidDate ? date?.toISOString() : undefined}
      style={{ visibility: timeZone ? "visible" : "hidden" }}
      title={timeZone ? `${label} (${timeZone})` : label}
    >
      {label}
    </time>
  );
}
