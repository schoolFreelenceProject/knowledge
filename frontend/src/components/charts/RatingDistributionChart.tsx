import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RatingDistributionItem } from "../../types/api";
import { EmptyState } from "../ui/StatusState";

export function RatingDistributionChart({
  data,
}: {
  data: RatingDistributionItem[];
}) {
  if (!data.length || data.every((item) => item.count === 0)) {
    return <EmptyState title="No rating distribution yet" />;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="rating" tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
          <Tooltip />
          <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
