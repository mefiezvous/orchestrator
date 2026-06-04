import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(async () => undefined),
}));

describe("createAuthedSSE", () => {
  beforeEach(() => {
    localStorage.setItem("orchestrator.api_token", "sse-token-xyz");
    vi.resetModules();
  });
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("passes Bearer header to fetchEventSource", async () => {
    const { fetchEventSource } = await import("@microsoft/fetch-event-source");
    const { createAuthedSSE } = await import("../api/sse");
    const controller = new AbortController();

    await createAuthedSSE("/api/v1/runs/foo/logs", {
      onMessage: () => undefined,
      signal: controller.signal,
    });

    expect(fetchEventSource).toHaveBeenCalledOnce();
    const [, init] = (fetchEventSource as unknown as { mock: { calls: [string, { headers: Record<string,string>; signal: AbortSignal }][] } }).mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer sse-token-xyz");
    expect(init.signal).toBe(controller.signal);
  });

  it("does not set Authorization when token is empty", async () => {
    localStorage.clear();
    const { fetchEventSource } = await import("@microsoft/fetch-event-source");
    const { createAuthedSSE } = await import("../api/sse");
    const controller = new AbortController();

    await createAuthedSSE("/api/v1/runs/bar/metrics", {
      onMessage: () => undefined,
      signal: controller.signal,
    });

    const [, init] = (fetchEventSource as unknown as { mock: { calls: [string, { headers: Record<string,string> }][] } }).mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });
});
