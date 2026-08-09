import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RetrievalModeDistributionItem } from "../../types/api";
import { EmptyState } from "../ui/StatusState";

export function RetrievalModeChart({
  data,
}: {
  data: RetrievalModeDistributionItem[];
}) {
  if (!data.length) {
    return <EmptyState title="No retrieval analytics yet" />;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="retrieval_mode" tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
          <Tooltip />
          <Bar dataKey="count" fill="#0f766e" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
