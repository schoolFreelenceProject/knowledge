import type { ReactNode } from "react";

import { Panel } from "./Panel";

export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <Panel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-normal text-muted">{label}</p>
          <div className="mt-2 truncate text-2xl font-semibold text-ink">{value}</div>
          {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
        </div>
        {icon ? <div className="text-muted">{icon}</div> : null}
      </div>
    </Panel>
  );
}
