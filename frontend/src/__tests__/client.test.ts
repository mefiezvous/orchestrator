import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("api client Bearer middleware", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.setItem("orchestrator.api_token", "test-token-abc");
  });
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  async function runWithMockFetch(call: () => Promise<unknown>): Promise<Request> {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    await call();
    expect(fetchMock).toHaveBeenCalledOnce();
    const firstCall = fetchMock.mock.calls[0] as unknown as [Request];
    return firstCall[0];
  }

  it("attaches Authorization: Bearer on protected endpoints", async () => {
    const { client } = await import("../api/client");
    const req = await runWithMockFetch(() => client.GET("/api/v1/runs/"));
    expect(req.headers.get("Authorization")).toBe("Bearer test-token-abc");
  });

  it("omits Authorization on /api/v1/health", async () => {
    const { client } = await import("../api/client");
    const req = await runWithMockFetch(() => client.GET("/api/v1/health"));
    expect(req.headers.get("Authorization")).toBeNull();
  });
});
