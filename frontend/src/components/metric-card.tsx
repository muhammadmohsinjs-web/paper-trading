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
    <div className="panel-soft p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-mist/55">{label}</p>
      <p
        className={cn(
          "mt-3 text-2xl font-semibold tracking-tight",
          accent === "gold" && "text-gold",
          accent === "rise" && "text-rise",
          accent === "fall" && "text-fall",
          accent === "mist" && "text-sand"
        )}
      >
        {value}
      </p>
      {detail ? <p className="mt-2 text-sm text-mist/60">{detail}</p> : null}
    </div>
  );
}
