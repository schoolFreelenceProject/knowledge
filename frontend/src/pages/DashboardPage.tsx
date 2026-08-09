import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Clock3,
  MessageSquare,
  Star,
  Users,
} from "lucide-react";

import { getAnalyticsSummary } from "../api/analytics";
import { getErrorMessage } from "../api/client";
import { listDocuments } from "../api/documents";
import { listUsers } from "../api/users";
import { PageHeader } from "../components/ui/PageHeader";
import { StatCard } from "../components/ui/StatCard";
import { ErrorState, LoadingState } from "../components/ui/StatusState";
import { UnavailableState } from "../components/ui/UnavailableState";
import { formatMs, formatNumber, formatRate, formatRating } from "../utils/format";

export function DashboardPage() {
  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });
  const summaryQuery = useQuery({
    queryKey: ["analytics", "summary", {}],
    queryFn: () => getAnalyticsSummary(),
  });
  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const isLoading = documentsQuery.isLoading || summaryQuery.isLoading || usersQuery.isLoading;
  const error = documentsQuery.error || summaryQuery.error || usersQuery.error;
  const documents = documentsQuery.data ?? [];
  const summary = summaryQuery.data;
  const users = usersQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Operational overview for the knowledge base."
      />

      {isLoading ? <LoadingState label="Loading dashboard metrics" /> : null}
      {error ? (
        <ErrorState
          title="Dashboard metrics failed"
          detail={getErrorMessage(error, "Unable to load dashboard metrics.")}
        />
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Documents"
          value={formatNumber(documents.length)}
          hint={`${formatNumber(documents.reduce((sum, item) => sum + item.chunk_count, 0))} chunks`}
          icon={<BookOpen className="h-5 w-5" />}
        />
        <StatCard
          label="Questions"
          value={formatNumber(summary?.total_questions)}
          hint="Recorded chat traces"
          icon={<MessageSquare className="h-5 w-5" />}
        />
        <StatCard
          label="Average Latency"
          value={formatMs(summary?.average_latency_ms)}
          hint="End-to-end chat latency"
          icon={<Clock3 className="h-5 w-5" />}
        />
        <StatCard
          label="Average Rating"
          value={formatRating(summary?.average_user_rating)}
          hint={`${formatNumber(summary?.feedback_count)} feedback rows`}
          icon={<Star className="h-5 w-5" />}
        />
        <StatCard
          label="Failed Answer Rate"
          value={formatRate(summary?.bad_answer_rate)}
          hint="Feedback rating <= 2"
          icon={<AlertTriangle className="h-5 w-5" />}
        />
        <StatCard
          label="Good Answer Rate"
          value={formatRate(summary?.good_answer_rate)}
          hint="Feedback rating >= 4"
          icon={<BarChart3 className="h-5 w-5" />}
        />
        <StatCard
          label="Users"
          value={formatNumber(users.length)}
          hint={`${formatNumber(users.filter((user) => user.is_active).length)} active`}
          icon={<Users className="h-5 w-5" />}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <UnavailableState
          title="Code repository count unavailable"
          reason="The backend currently exposes repository ingestion only, not repository listing."
        />
      </section>
    </div>
  );
}
