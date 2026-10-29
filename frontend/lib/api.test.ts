import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { api, ApiConnectionError, ApiResponseError } from "@/lib/api";

describe("typed API client", () => {
  it("returns parsed successful responses", async (context) => {
    context.mock.method(globalThis, "fetch", async () =>
      new Response(JSON.stringify({ status: "ok", service: "RevSignal" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    assert.deepEqual(await api.health(), { status: "ok", service: "RevSignal" });
  });

  it("surfaces backend validation messages", async (context) => {
    context.mock.method(globalThis, "fetch", async () =>
      new Response(JSON.stringify({ detail: "Missing required columns: stage." }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await assert.rejects(api.health(), (error: unknown) =>
      error instanceof ApiResponseError &&
      error.status === 400 &&
      error.message === "Missing required columns: stage.",
    );
  });

  it("identifies a disconnected backend for demo-mode handling", async (context) => {
    context.mock.method(globalThis, "fetch", async () => {
      throw new TypeError("fetch failed");
    });
    await assert.rejects(api.health(), (error: unknown) =>
      error instanceof ApiConnectionError && error.message.includes("Cannot reach"),
    );
  });
});
