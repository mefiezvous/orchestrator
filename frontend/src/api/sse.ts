import { fetchEventSource } from "@microsoft/fetch-event-source";
import { getApiBase, getToken } from "./token";

export interface SSEOptions {
  onMessage: (data: string) => void;
  onError?: (err: unknown) => void;
  onOpen?: () => void;
  signal: AbortSignal;
}

export async function createAuthedSSE(path: string, opts: SSEOptions): Promise<void> {
  const base = getApiBase();
  const url = base ? `${base}${path}` : path;
  const token = getToken();
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (token) headers.Authorization = `Bearer ${token}`;

  await fetchEventSource(url, {
    headers,
    signal: opts.signal,
    openWhenHidden: true,
    onopen: async (response) => {
      if (response.ok && response.headers.get("content-type")?.includes("text/event-stream")) {
        opts.onOpen?.();
        return;
      }
      throw new Error(`SSE failed to open: ${response.status} ${response.statusText}`);
    },
    onmessage: (ev) => {
      if (ev.data) opts.onMessage(ev.data);
    },
    onerror: (err) => {
      opts.onError?.(err);
      throw err;
    },
  });
}
