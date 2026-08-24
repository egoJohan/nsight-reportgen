import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { classifyLockFailure, lockFailureMessage } from "./reportLock";

describe("what a failed lock request means", () => {
  it("treats a 409 as somebody else holding the report", () => {
    expect(classifyLockFailure(new ApiError(409, "Locked by Maija"))).toBe("taken");
  });

  it("does not close the editor because the network dropped", () => {
    // What fetch() rejects with when the connection fails. This case closed the
    // editor and discarded unsaved slides.
    expect(classifyLockFailure(new TypeError("Failed to fetch"))).toBe("unreachable");
  });

  it("does not close the editor because the server erred", () => {
    expect(classifyLockFailure(new ApiError(500, "Internal Server Error"))).toBe(
      "unreachable"
    );
    expect(classifyLockFailure(new ApiError(504, "Gateway Timeout"))).toBe(
      "unreachable"
    );
  });

  it("does not close the editor on something it cannot read at all", () => {
    expect(classifyLockFailure(undefined)).toBe("unreachable");
    expect(classifyLockFailure("nope")).toBe("unreachable");
  });
});

describe("a report that is not ours to edit any more", () => {
  it("treats a deleted case or report as a reason to close", () => {
    // require_case_write 404s when the case is gone or was never visible.
    expect(classifyLockFailure(new ApiError(404, "Case 'x' not found"))).toBe("gone");
  });

  it("treats a revoked grant the same way", () => {
    expect(classifyLockFailure(new ApiError(403, "Not permitted"))).toBe("gone");
  });

  it("says something an author can act on", () => {
    expect(lockFailureMessage("gone", "Someone else is editing this report."))
      .toMatch(/no longer available/i);
    // A real lock keeps the server's message, which names the holder.
    expect(lockFailureMessage("taken", "Maija is editing this report."))
      .toBe("Maija is editing this report.");
  });

  it("still keeps the editor open for a failure to find out", () => {
    expect(classifyLockFailure(new ApiError(500, "boom"))).toBe("unreachable");
    expect(classifyLockFailure(new ApiError(502, "bad gateway"))).toBe("unreachable");
    expect(classifyLockFailure(new TypeError("Failed to fetch"))).toBe("unreachable");
  });
});
