import { useQuery } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useMemo, useState } from "react";

import { getFeedbackAnalytics } from "../api/analytics";
import { getErrorMessage } from "../api/client";
import { listFeedback } from "../api/feedback";
import { RatingDistributionChart } from "../components/charts/RatingDistributionChart";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusState";
import { StatCard } from "../components/ui/StatCard";
import { formatDateTime, formatNumber, formatRate, formatRating } from "../utils/format";
import { compactParams } from "../utils/params";

const PAGE_SIZE = 50;

export function FeedbackPage() {
  const [rating, setRating] = useState("");
  const [requestId, setRequestId] = useState("");
  const [offset, setOffset] = useState(0);

  const feedbackParams = useMemo(
    () =>
      compactParams({
        limit: PAGE_SIZE,
        offset,
        rating: rating ? Number(rating) : undefined,
        request_id: requestId || undefined,
      }),
    [offset, rating, requestId],
  );

  const feedbackQuery = useQuery({
    queryKey: ["feedback", feedbackParams],
    queryFn: () => listFeedback(feedbackParams),
  });
  const analyticsQuery = useQuery({
    queryKey: ["analytics", "feedback", {}],
    queryFn: () => getFeedbackAnalytics(),
  });

  const badFeedback = (feedbackQuery.data?.items ?? []).filter(
    (item) => item.rating <= 2,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Feedback"
        description="Review user ratings and comments linked to RAG traces."
      />

      {analyticsQuery.error || feedbackQuery.error ? (
        <ErrorState
          title="Feedback request failed"
          detail={getErrorMessage(
            analyticsQuery.error || feedbackQuery.error,
            "Unable to load feedback.",
          )}
        />
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Feedback Count"
          value={formatNumber(analyticsQuery.data?.feedback_count)}
          hint="Total feedback rows"
          icon={<Star className="h-5 w-5" />}
        />
        <StatCard
          label="Average Rating"
          value={formatRating(analyticsQuery.data?.average_user_rating)}
          hint="Mean rating"
        />
        <StatCard
          label="Bad Answer Rate"
          value={formatRate(analyticsQuery.data?.bad_answer_rate)}
          hint="Rating <= 2"
        />
        <StatCard
          label="Good Answer Rate"
          value={formatRate(analyticsQuery.data?.good_answer_rate)}
          hint="Rating >= 4"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Panel>
          <PanelHeader title="Rating Distribution" />
          <div className="p-4">
            {analyticsQuery.isLoading ? <LoadingState /> : null}
            {analyticsQuery.data ? (
              <RatingDistributionChart data={analyticsQuery.data.rating_distribution} />
            ) : null}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Bad Answer Review" />
          <div className="space-y-3 p-4">
            {badFeedback.length ? (
              badFeedback.map((item) => (
                <article key={item.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <Badge tone="danger">{item.rating} stars</Badge>
                    <span className="font-mono text-xs text-muted">{item.request_id}</span>
                  </div>
                  <p className="mt-2 text-sm text-ink">{item.comment || "No comment"}</p>
                  <p className="mt-2 text-xs text-muted">{formatDateTime(item.created_at)}</p>
                </article>
              ))
            ) : (
              <EmptyState title="No bad feedback in current result page" />
            )}
          </div>
        </Panel>
      </section>

      <Panel>
        <PanelHeader
          title="Feedback Records"
          actions={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={(feedbackQuery.data?.items.length ?? 0) < PAGE_SIZE}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          }
        />
        <div className="grid gap-3 border-b border-border p-4 md:grid-cols-3">
          <select className="form-input" value={rating} onChange={(event) => setRating(event.target.value)}>
            <option value="">All ratings</option>
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>{value} stars</option>
            ))}
          </select>
          <input
            className="form-input md:col-span-2"
            value={requestId}
            onChange={(event) => setRequestId(event.target.value)}
            placeholder="Request ID"
          />
        </div>
        {feedbackQuery.isLoading ? <div className="p-4"><LoadingState /></div> : null}
        {(feedbackQuery.data?.items.length ?? 0) > 0 ? (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rating</th>
                  <th>Request</th>
                  <th>User</th>
                  <th>Comment</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {feedbackQuery.data?.items.map((item) => (
                  <tr key={item.id}>
                    <td><FeedbackBadge rating={item.rating} /></td>
                    <td className="font-mono text-xs">{item.request_id}</td>
                    <td>{item.user_id}</td>
                    <td className="max-w-md truncate">{item.comment || "-"}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !feedbackQuery.isLoading ? (
          <div className="p-4">
            <EmptyState title="No feedback records found" />
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function FeedbackBadge({ rating }: { rating: number }) {
  const tone = rating <= 2 ? "danger" : rating >= 4 ? "success" : "warning";
  return <Badge tone={tone}>{rating} stars</Badge>;
}
