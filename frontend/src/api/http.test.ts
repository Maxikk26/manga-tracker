import { describe, expect, it } from "vitest";
import { ApiError, readDetail } from "./http";

function jsonResponse(body: unknown, status = 409): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("readDetail", () => {
  it("parses a plain detail string with no existing key", async () => {
    const { detail, existing } = await readDetail(jsonResponse({ detail: "boom" }));
    expect(detail).toBe("boom");
    expect(existing).toBeUndefined();
  });

  it("parses the existing sibling key on a 409", async () => {
    const { detail, existing } = await readDetail(
      jsonResponse({
        detail: "«Berserk» ya está en tu lista, con estado Abandonado.",
        existing: { title: "Berserk", status: "dropped", terminal: true },
      }),
    );
    expect(detail).toContain("Berserk");
    expect(existing).toEqual({ title: "Berserk", status: "dropped", terminal: true });
  });

  it("ignores an existing value missing required fields", async () => {
    const { existing } = await readDetail(
      jsonResponse({ detail: "x", existing: { title: "x" } }),
    );
    expect(existing).toBeUndefined();
  });

  it("returns a null detail and no existing on an unparsable body", async () => {
    const response = new Response("not json", { status: 500 });
    const { detail, existing } = await readDetail(response);
    expect(detail).toBeNull();
    expect(existing).toBeUndefined();
  });
});

describe("ApiError", () => {
  it("carries the existing payload when provided", () => {
    const error = new ApiError("msg", { title: "t", status: "dropped", terminal: true });
    expect(error.message).toBe("msg");
    expect(error.existing).toEqual({ title: "t", status: "dropped", terminal: true });
  });

  it("leaves existing undefined by default", () => {
    const error = new ApiError("msg");
    expect(error.existing).toBeUndefined();
  });
});
