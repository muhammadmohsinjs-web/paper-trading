import { cn } from "@/lib/format";

type StatusPillProps = {
  tone: "rise" | "fall" | "muted" | "gold";
  children: React.ReactNode;
};

const toneMap = {
  rise: "bg-rise/14 text-rise ring-rise/30",
  fall: "bg-fall/14 text-fall ring-fall/30",
  muted: "bg-white/8 text-mist ring-white/10",
  gold: "bg-gold/16 text-gold ring-gold/30"
} as const;

export function StatusPill({ tone, children }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ring-1",
        toneMap[tone]
      )}
    >
      {children}
    </span>
  );
}
