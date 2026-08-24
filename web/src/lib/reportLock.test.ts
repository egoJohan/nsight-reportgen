import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { classifyLockFailure } from "./reportLock";

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
