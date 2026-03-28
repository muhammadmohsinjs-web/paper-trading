import { cn, getCoinIconUrl } from "@/lib/format";

type SurfaceProps = React.ComponentPropsWithoutRef<"section"> & {
  tone?: "default" | "subtle";
};

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
};

type SectionHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  compact?: boolean;
};

type MetricRowProps = {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  tone?: "default" | "success" | "danger" | "warning" | "accent";
};

type MetricStripProps = {
  items: { label: string; value: React.ReactNode; tone?: MetricRowProps["tone"] }[];
  className?: string;
};

type StatusBadgeProps = {
  tone?: "neutral" | "accent" | "success" | "danger" | "warning";
  children: React.ReactNode;
  className?: string;
};

type ButtonVariant = "primary" | "secondary" | "tertiary" | "danger";
type ButtonSize = "sm" | "md";

export function surfaceClassName(
  tone: SurfaceProps["tone"] = "default",
  className?: string
) {
  return cn(
    "rounded-xl border border-slate-200/60 bg-white transition-colors",
    tone === "subtle" && "bg-slate-50/80",
    className
  );
}

export function buttonClassName(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  className?: string
) {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 disabled:cursor-not-allowed disabled:opacity-60",
    size === "sm" ? "px-3 py-2 text-sm" : "px-4 py-2.5 text-sm",
    variant === "primary" && "bg-blue-700 text-white hover:bg-blue-800",
    variant === "secondary" &&
      "border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
    variant === "tertiary" && "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
    variant === "danger" &&
      "border border-red-200 bg-red-50 text-red-700 hover:border-red-300 hover:bg-red-100",
    className
  );
}

export function badgeClassName(
  tone: StatusBadgeProps["tone"] = "neutral",
  className?: string
) {
  return cn(
    "inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[11px] font-medium",
    tone === "neutral" && "bg-slate-100 text-slate-600",
    tone === "accent" && "bg-blue-50 text-blue-700",
    tone === "success" && "bg-emerald-50 text-emerald-700",
    tone === "danger" && "bg-red-50 text-red-700",
    tone === "warning" && "bg-amber-50 text-amber-700",
    className
  );
}

export function Surface({ tone = "default", className, ...props }: SurfaceProps) {
  return <section className={surfaceClassName(tone, className)} {...props} />;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0 space-y-1.5">
        <h1 className="text-2xl font-semibold leading-tight tracking-[-0.03em] text-slate-900">
          {title}
        </h1>
        {description ? (
          <p className="max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  action,
  compact = false
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2",
        compact ? "px-5 py-3" : "px-6 py-3",
        action ? "lg:flex-row lg:items-end lg:justify-between" : ""
      )}
    >
      <div className="min-w-0">
        <h2 className="text-lg font-semibold leading-7 text-slate-900">{title}</h2>
        {description ? <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p> : null}
      </div>
      {action ? <div className="flex flex-wrap items-center gap-3">{action}</div> : null}
    </div>
  );
}

export function MetricRow({ label, value, detail, tone = "default" }: MetricRowProps) {
  return (
    <div className="space-y-1 py-2">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p
        className={cn(
          "text-xl font-semibold leading-tight tracking-[-0.03em] tabular-nums",
          tone === "default" && "text-slate-900",
          tone === "success" && "text-emerald-700",
          tone === "danger" && "text-red-700",
          tone === "warning" && "text-amber-700",
          tone === "accent" && "text-blue-700"
        )}
      >
        {value}
      </p>
      {detail ? <p className="text-sm leading-6 text-slate-600">{detail}</p> : null}
    </div>
  );
}

export function MetricStrip({ items, className }: MetricStripProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-4", className)}>
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-slate-200/60 bg-white px-4 py-3.5 space-y-1"
        >
          <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-slate-400">
            {item.label}
          </p>
          <p
            className={cn(
              "text-lg font-semibold tabular-nums tracking-[-0.02em]",
              (!item.tone || item.tone === "default") && "text-slate-900",
              item.tone === "success" && "text-emerald-600",
              item.tone === "danger" && "text-red-600",
              item.tone === "warning" && "text-amber-600",
              item.tone === "accent" && "text-blue-600"
            )}
          >
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ tone = "neutral", children, className }: StatusBadgeProps) {
  return <span className={badgeClassName(tone, className)}>{children}</span>;
}

export function CoinIcon({ symbol, size = 20 }: { symbol: string; size?: number }) {
  return (
    <img
      src={getCoinIconUrl(symbol)}
      alt=""
      width={size}
      height={size}
      className="shrink-0 rounded-full"
      onError={(e) => {
        (e.currentTarget as HTMLImageElement).style.display = "none";
      }}
    />
  );
}
