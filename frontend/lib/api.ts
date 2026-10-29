import type { Deal, Metrics, UploadResponse } from "@/lib/types";

const API_BASE_URL =
  process.env.NODE_ENV === "development"
    ? (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(
        /\/+$/,
        "",
      )
    : "";

export class ApiConnectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConnectionError";
  }
}

export class ApiResponseError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiResponseError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 8_000,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        signal: controller.signal,
        cache: "no-store",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiConnectionError("The API request timed out. Check that the backend is running and try again.");
      }
      throw new ApiConnectionError(
        `Cannot reach the RevSignal API at ${API_BASE_URL}. Start the backend to use live data.`,
      );
    }

    if (!response.ok) {
      let message = `The API returned an error (${response.status}).`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) message = body.detail;
      } catch {
        // Keep the status-based message when the response is not JSON.
      }
      throw new ApiResponseError(message, response.status);
    }

    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  health: () =>
    request<{ status: string; service: string }>(
      API_BASE_URL ? "/health" : "/api/health",
    ),
  deals: () => request<Deal[]>("/api/deals"),
  metrics: () => request<Metrics>("/api/metrics"),
  deal: (dealId: string) => request<Deal>(`/api/deals/${encodeURIComponent(dealId)}`),
  analyze: (dealId: string) =>
    request<Deal>(`/api/deals/${encodeURIComponent(dealId)}/analyze`, {
      method: "POST",
    }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<UploadResponse>(
      "/api/deals/upload",
      { method: "POST", body },
      30_000,
    );
  },
};
