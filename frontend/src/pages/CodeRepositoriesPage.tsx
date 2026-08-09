import { useMutation } from "@tanstack/react-query";
import { Code2, GitBranch, UploadCloud } from "lucide-react";
import { useState } from "react";

import { ingestCodeRepository } from "../api/code";
import { getErrorMessage } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { ErrorState } from "../components/ui/StatusState";
import { StatCard } from "../components/ui/StatCard";
import { UnavailableState } from "../components/ui/UnavailableState";
import type { CodeIngestResponse } from "../types/api";
import { compactHash, formatNumber } from "../utils/format";

export function CodeRepositoriesPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [lastResult, setLastResult] = useState<CodeIngestResponse | null>(null);

  const ingestMutation = useMutation({
    mutationFn: ingestCodeRepository,
    onSuccess: (response) => setLastResult(response),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Code Repository"
        description="Index source code into the unified RAG retrieval collection."
      />

      {ingestMutation.error ? (
        <ErrorState
          title="Repository ingestion failed"
          detail={getErrorMessage(ingestMutation.error, "Unable to ingest repository.")}
        />
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
        <Panel>
          <PanelHeader title="Ingest Repository" />
          <form
            className="space-y-4 p-4"
            onSubmit={(event) => {
              event.preventDefault();
              ingestMutation.mutate({
                repo_url: repoUrl.trim(),
                branch: branch.trim() || "main",
              });
            }}
          >
            <label className="block space-y-1">
              <span className="form-label">Repository URL</span>
              <input
                className="form-input"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/company/repository.git"
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="form-label">Branch</span>
              <input
                className="form-input"
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                required
              />
            </label>
            <Button
              type="submit"
              icon={<UploadCloud className="h-4 w-4" />}
              isLoading={ingestMutation.isPending}
            >
              Ingest Repository
            </Button>
          </form>
        </Panel>

        <div className="space-y-4">
          <UnavailableState
            title="Repository inventory unavailable"
            reason="The backend currently exposes repository ingestion only, not listing or detail endpoints."
          />
          <UnavailableState
            title="Repository reindex unavailable"
            reason="A code repository reindex endpoint is not exposed by the current backend API."
          />
          <UnavailableState
            title="Repository permissions unavailable"
            reason="The current permission endpoints cover documents only."
          />
        </div>
      </section>

      {lastResult ? (
        <section className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Repository"
              value={lastResult.repo_name}
              hint={`ID ${lastResult.repository_id}`}
              icon={<Code2 className="h-5 w-5" />}
            />
            <StatCard
              label="Branch"
              value={lastResult.branch}
              hint={compactHash(lastResult.commit_sha, 10)}
              icon={<GitBranch className="h-5 w-5" />}
            />
            <StatCard
              label="Files"
              value={formatNumber(lastResult.files)}
              hint={`${formatNumber(lastResult.chunks)} chunks`}
            />
            <StatCard
              label="Vectors"
              value={formatNumber(lastResult.stored_vectors)}
              hint={lastResult.collection_name}
            />
          </div>
          <Panel>
            <PanelHeader
              title="Latest Ingest Result"
              actions={<Badge tone="success">{lastResult.status}</Badge>}
            />
            <dl className="grid gap-3 p-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <Detail label="Repository URL" value={lastResult.repo_url} />
              <Detail label="Storage Path" value={lastResult.storage_path} />
              <Detail label="Commit SHA" value={lastResult.commit_sha} />
              <Detail label="Embeddings" value={formatNumber(lastResult.embeddings)} />
              <Detail label="Saved Chunks" value={formatNumber(lastResult.saved_chunks)} />
              <Detail label="Vector Size" value={formatNumber(lastResult.vector_size)} />
            </dl>
          </Panel>
        </section>
      ) : null}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="form-label">{label}</dt>
      <dd className="mt-1 truncate text-ink">{value}</dd>
    </div>
  );
}
