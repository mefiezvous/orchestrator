const STORAGE_KEY = "orchestrator.api_token";

export function getToken(): string {
  const envToken = (import.meta.env.VITE_API_TOKEN as string | undefined) ?? "";
  if (envToken) return envToken;
  return localStorage.getItem(STORAGE_KEY) ?? "";
}

export function setToken(value: string): void {
  localStorage.setItem(STORAGE_KEY, value);
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function getApiBase(): string {
  return (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
}
