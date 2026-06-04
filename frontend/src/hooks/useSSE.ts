import { useEffect } from "react";
import { createAuthedSSE } from "../api/sse";

export function useSSE(path: string | null, onMessage: (data: string) => void) {
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    createAuthedSSE(path, { onMessage, signal: controller.signal }).catch((err) => {
      if (controller.signal.aborted) return;
      console.error("[SSE]", path, err);
    });
    return () => controller.abort();
  }, [path, onMessage]);
}
