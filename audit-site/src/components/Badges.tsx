export type Severity = "critical" | "high" | "medium" | "low" | "positive";

const styles: Record<Severity, string> = {
  critical: "bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-500/30",
  high: "bg-orange-500/15 text-orange-300 ring-1 ring-inset ring-orange-500/30",
  medium: "bg-amber-500/15 text-amber-300 ring-1 ring-inset ring-amber-500/30",
  low: "bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-500/30",
  positive: "bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-500/30",
};

const labels: Record<Severity, string> = {
  critical: "Критично",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
  positive: "Позитивно",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[severity]}`}>
      {labels[severity]}
    </span>
  );
}

export function GradeBadge({ grade }: { grade: string }) {
  const color = grade.startsWith("A")
    ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30"
    : grade.startsWith("B")
    ? "bg-teal-500/15 text-teal-300 ring-teal-500/30"
    : grade.startsWith("C")
    ? "bg-amber-500/15 text-amber-300 ring-amber-500/30"
    : "bg-red-500/15 text-red-300 ring-red-500/30";
  return (
    <span className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold ring-1 ring-inset ${color}`}>
      {grade}
    </span>
  );
}
