import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./generated/types.gen";
import { getApiBase, getToken } from "./token";

// Paths that must NOT carry the Bearer token.
const UNAUTHENTICATED_PATHS = ["/api/v1/health"];

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const url = new URL(request.url);
    if (UNAUTHENTICATED_PATHS.some((p) => url.pathname.startsWith(p))) {
      return request;
    }
    const token = getToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
};

function defaultBaseUrl(): string {
  const configured = getApiBase();
  if (configured) return configured;
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "http://localhost";
}

export const client = createClient<paths>({
  baseUrl: defaultBaseUrl(),
  // Dispatch through globalThis at call time so tests can intercept via
  // vi.stubGlobal("fetch", ...). openapi-fetch otherwise captures whatever
  // fetch is bound at module-evaluation time.
  fetch: (input: Request) => globalThis.fetch(input),
});

client.use(authMiddleware);
