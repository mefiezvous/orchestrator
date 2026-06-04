import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";

export interface RunFilters {
  status?: string;
  job_type?: string;
  limit?: number;
}

export function useRuns(filters: RunFilters) {
  return useQuery({
    queryKey: ["runs", filters],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/runs/", {
        params: { query: filters },
      });
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    refetchInterval: (q) => {
      const rows = (q.state.data as { status: string }[] | undefined) ?? [];
      const active = rows.some((r) => r.status === "queued" || r.status === "running");
      return active ? 5_000 : false;
    },
  });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["run", runId],
    enabled: !!runId,
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/runs/{run_id}", {
        params: { path: { run_id: runId! } },
      });
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    refetchInterval: (q) => {
      const status = (q.state.data as { status?: string } | undefined)?.status;
      return status === "queued" || status === "running" ? 3_000 : false;
    },
  });
}
