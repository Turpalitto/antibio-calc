export function Donut({
  data,
}: {
  data: { label: string; value: number; pct: number; color: string }[];
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  let cumulative = 0;
  const radius = 15.9155;
  const circumference = 2 * Math.PI * radius;

  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
      <svg viewBox="0 0 36 36" className="h-44 w-44 shrink-0 -rotate-90">
        <circle cx="18" cy="18" r={radius} fill="none" stroke="#1e293b" strokeWidth="4" />
        {data.map((d) => {
          const dash = (d.value / total) * circumference;
          const offset = (cumulative / total) * circumference;
          cumulative += d.value;
          return (
            <circle
              key={d.label}
              cx="18"
              cy="18"
              r={radius}
              fill="none"
              stroke={d.color}
              strokeWidth="4"
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
            />
          );
        })}
      </svg>
      <div className="space-y-3">
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-3">
            <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: d.color }} />
            <span className="text-sm text-slate-300">
              <span className="font-semibold text-white">{d.label}</span> — {d.value} ({d.pct}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BarList({ data }: { data: { field: string; pct: number }[] }) {
  return (
    <div className="space-y-4">
      {data.map((d) => (
        <div key={d.field}>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-slate-300">{d.field}</span>
            <span className="font-semibold text-white">{d.pct}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full ${
                d.pct >= 70 ? "bg-emerald-500" : d.pct >= 40 ? "bg-amber-500" : "bg-red-500"
              }`}
              style={{ width: `${Math.max(d.pct, 2)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
