// SPDX-FileCopyrightText: 2026 Arthur Mouraud
// SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { client } from "../api/client";
import type { components } from "../api/generated/types.gen";

export type RobotSpecResponse = components["schemas"]["RobotSpecResponse"];
export type LineageNodeResponse = components["schemas"]["LineageNodeResponse"];
export type RobotSpecCreateRequest = components["schemas"]["RobotSpecCreateRequest"];
export type RobotSpecBranchRequest = components["schemas"]["RobotSpecBranchRequest"];

export function useRobots() {
  return useQuery({
    queryKey: ["robots"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/robots/");
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
  });
}

export function useRobotLineage() {
  return useQuery({
    queryKey: ["robots", "lineage"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/robots/lineage");
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
  });
}

export function useCreateRobot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: RobotSpecCreateRequest) => {
      const { data, error } = await client.POST("/api/v1/robots/", { body });
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["robots"] });
    },
  });
}

export function useBranchRobot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      parentId,
      body,
    }: {
      parentId: string;
      body: RobotSpecBranchRequest;
    }) => {
      const { data, error } = await client.POST("/api/v1/robots/{parent_id}/branch", {
        params: { path: { parent_id: parentId } },
        body,
      });
      if (error) throw new Error(JSON.stringify(error));
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["robots"] });
    },
  });
}
