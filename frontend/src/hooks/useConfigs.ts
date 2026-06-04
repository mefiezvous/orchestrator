import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";

type ConfigKind = "envs" | "policies" | "profiles" | "datasets" | "collect" | "eval";

const paths: Record<ConfigKind, "/api/v1/configs/envs" | "/api/v1/configs/policies" | "/api/v1/configs/profiles" | "/api/v1/configs/datasets" | "/api/v1/configs/collect" | "/api/v1/configs/eval"> = {
  envs: "/api/v1/configs/envs",
  policies: "/api/v1/configs/policies",
  profiles: "/api/v1/configs/profiles",
  datasets: "/api/v1/configs/datasets",
  collect: "/api/v1/configs/collect",
  eval: "/api/v1/configs/eval",
};

export function useConfigs(kind: ConfigKind) {
  return useQuery({
    queryKey: ["configs", kind],
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const { data, error } = await client.GET(paths[kind]);
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
  });
}
