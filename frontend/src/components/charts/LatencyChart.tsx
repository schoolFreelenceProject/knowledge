import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TraceRecord } from "../../types/api";
import { formatMs } from "../../utils/format";
import { EmptyState } from "../ui/StatusState";

export function LatencyChart({ data }: { data: TraceRecord[] }) {
  const chartData = data
    .filter((trace) => trace.total_time_ms !== null)
    .slice(0, 20)
    .reverse()
    .map((trace) => ({
      request: trace.request_id.slice(0, 8),
      latency: trace.total_time_ms ?? 0,
    }));

  if (!chartData.length) {
    return <EmptyState title="No latency rows yet" />;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="request" tickLine={false} axisLine={false} />
          <YAxis tickFormatter={(value) => formatMs(Number(value))} tickLine={false} axisLine={false} />
          <Tooltip formatter={(value) => formatMs(Number(value))} />
          <Bar dataKey="latency" fill="#7c3aed" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
