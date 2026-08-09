import { AlertCircle, Inbox, Loader2 } from "lucide-react";

import { Panel } from "./Panel";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  return (
    <Panel className="flex items-start gap-3 p-4">
      <Inbox className="mt-0.5 h-5 w-5 text-muted" />
      <div>
        <p className="text-sm font-medium text-ink">{title}</p>
        {detail ? <p className="mt-1 text-sm text-muted">{detail}</p> : null}
      </div>
    </Panel>
  );
}

export function ErrorState({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  return (
    <Panel className="flex items-start gap-3 border-red-200 bg-red-50 p-4">
      <AlertCircle className="mt-0.5 h-5 w-5 text-red-600" />
      <div>
        <p className="text-sm font-medium text-red-800">{title}</p>
        {detail ? <p className="mt-1 text-sm text-red-700">{detail}</p> : null}
      </div>
    </Panel>
  );
}
