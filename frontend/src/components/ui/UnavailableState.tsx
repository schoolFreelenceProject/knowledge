import { LockKeyhole } from "lucide-react";

import { Panel } from "./Panel";

export function UnavailableState({
  title,
  reason,
}: {
  title: string;
  reason: string;
}) {
  return (
    <Panel className="flex items-start gap-3 border-dashed p-4">
      <LockKeyhole className="mt-0.5 h-5 w-5 text-muted" />
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="mt-1 text-sm text-muted">{reason}</p>
      </div>
    </Panel>
  );
}
