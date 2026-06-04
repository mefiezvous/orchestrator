import { useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRun } from "../hooks/useRuns";
import { LogStream } from "../components/LogStream";
import { MetricsChart } from "../components/MetricsChart";
import { RunStatusBadge } from "../components/RunStatusBadge";
import { client } from "../api/client";

export function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, error } = useRun(id);
  const queryClient = useQueryClient();

  const cancel = useMutation({
    mutationFn: async () => {
      const { error: err } = await client.DELETE("/api/v1/runs/{run_id}", {
        params: { path: { run_id: id! } },
      });
      if (err) throw new Error(JSON.stringify(err));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  if (isLoading) return <div className="loading loading-spinner" />;
  if (error) return <div className="alert alert-error">{(error as Error).message}</div>;
  if (!run || !id) return null;

  const canCancel = run.status === "queued" || run.status === "running";

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Run {id.slice(0, 8)}</h1>
          <div className="flex gap-3 mt-1 text-sm">
            <span>{run.job_type}</span>
            <RunStatusBadge status={run.status} />
            <span className="opacity-70">{run.created_at}</span>
          </div>
        </div>
        {canCancel && (
          <button
            className="btn btn-warning btn-sm"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
          >
            Cancel
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section>
          <h2 className="font-semibold mb-2">Logs</h2>
          <LogStream runId={id} />
        </section>
        <section>
          <h2 className="font-semibold mb-2">Metrics</h2>
          <MetricsChart runId={id} />
        </section>
      </div>
      <details className="mt-6">
        <summary className="cursor-pointer font-semibold">Details</summary>
        <pre className="bg-base-200 p-3 mt-2 text-xs overflow-x-auto rounded">
          {JSON.stringify(run, null, 2)}
        </pre>
      </details>
    </div>
  );
}
