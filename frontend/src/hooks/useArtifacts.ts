import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { client } from "../api/client";
import type { components } from "../api/generated/types.gen";

type Checkpoint = components["schemas"]["CheckpointResponse"];
type EvalReport = components["schemas"]["EvalReportResponse"];
type Dataset = components["schemas"]["DatasetResponse"];

export function useCheckpoints(): UseQueryResult<Checkpoint[]> {
  return useQuery({
    queryKey: ["artifacts", "checkpoints"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/artifacts/checkpoints");
      if (error) throw new Error(JSON.stringify(error));
      return data as Checkpoint[];
    },
  });
}

export function useEvalReports(): UseQueryResult<EvalReport[]> {
  return useQuery({
    queryKey: ["artifacts", "eval-reports"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/artifacts/eval-reports");
      if (error) throw new Error(JSON.stringify(error));
      return data as EvalReport[];
    },
  });
}

export function useDatasets(): UseQueryResult<Dataset[]> {
  return useQuery({
    queryKey: ["artifacts", "datasets"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/artifacts/datasets");
      if (error) throw new Error(JSON.stringify(error));
      return data as Dataset[];
    },
  });
}
