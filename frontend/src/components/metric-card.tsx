import { cn } from "@/lib/format";

type MetricCardProps = {
  label: string;
  value: string;
  detail?: string;
  accent?: "gold" | "rise" | "fall" | "mist";
};

export function MetricCard({
  label,
  value,
  detail,
  accent = "mist"
}: MetricCardProps) {
  return (
    <div className="panel-soft relative overflow-hidden p-5">
      <div
        className={cn(
          "absolute inset-x-5 top-0 h-px",
          accent === "gold" && "bg-gold/60",
          accent === "rise" && "bg-rise/70",
          accent === "fall" && "bg-fall/70",
          accent === "mist" && "bg-white/20"
        )}
      />
      <p className="text-[11px] uppercase tracking-[0.26em] text-mist/48">{label}</p>
      <p
        className={cn(
          "mt-4 min-w-0 text-[clamp(2rem,3vw,2.65rem)] font-semibold leading-none tracking-[-0.04em]",
          accent === "gold" && "text-gold",
          accent === "rise" && "text-rise",
          accent === "fall" && "text-fall",
          accent === "mist" && "text-sand"
        )}
      >
        {value}
      </p>
      {detail ? <p className="mt-2 min-h-[2.75rem] text-sm leading-6 text-mist/62">{detail}</p> : null}
    </div>
  );
}
