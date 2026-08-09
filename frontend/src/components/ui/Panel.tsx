import type { ReactNode } from "react";

import { cn } from "../../utils/cn";

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-white shadow-panel",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function PanelHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {description ? <p className="mt-1 text-xs text-muted">{description}</p> : null}
      </div>
      {actions}
    </div>
  );
}
