export function formatCurrency(value: number | null | undefined, compact = false) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 2 : 2
  }).format(value);
}

export function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(digits)}%`;
}

export function formatDateTime(
  value: string | null | undefined,
  options?: Intl.DateTimeFormatOptions
) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  const hasExplicitParts = Boolean(
    options &&
      (
        options.weekday ||
        options.era ||
        options.year ||
        options.month ||
        options.day ||
        options.dayPeriod ||
        options.hour ||
        options.minute ||
        options.second ||
        options.fractionalSecondDigits ||
        options.timeZoneName
      )
  );

  const formatOptions = hasExplicitParts
    ? options
    : {
        dateStyle: "medium" as const,
        timeStyle: "short" as const,
        ...options
      };

  return new Intl.DateTimeFormat("en-US", formatOptions).format(date);
}

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}
