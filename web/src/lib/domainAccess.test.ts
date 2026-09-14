import { describe, expect, it } from "vitest";

import { saveBody, toRows, toStored } from "./domainAccess";

const EMPTY = { allowed_domains: [], domain_access: [], default_grants: [] };

describe("toRows", () => {
  it("merges the two lists into one row per domain", () => {
    expect(toRows({
      ...EMPTY,
      allowed_domains: ["nsight.fi"],
      domain_access: [{ domain: "nsight.fi", mode: "edit" }],
    })).toEqual([{ domain: "nsight.fi", signIn: true, mode: "edit" }]);
  });

  it("shows a domain that may sign in but is owed nothing", () => {
    expect(toRows({ ...EMPTY, allowed_domains: ["nsight.fi"] })).toEqual([
      { domain: "nsight.fi", signIn: true, mode: "none" },
    ]);
  });

  it("shows a domain that is owed access but may not sign itself in", () => {
    expect(toRows({ ...EMPTY, domain_access: [{ domain: "partner.com", mode: "view" }] }))
      .toEqual([{ domain: "partner.com", signIn: false, mode: "view" }]);
  });

  it("keeps the sign-in list's order and appends access-only domains", () => {
    expect(toRows({
      ...EMPTY,
      allowed_domains: ["b.fi", "a.fi"],
      domain_access: [{ domain: "c.fi", mode: "view" }],
    }).map((r) => r.domain)).toEqual(["b.fi", "a.fi", "c.fi"]);
  });

  it("reads a mode left in the sign-in list by the screen that had one list", () => {
    expect(toRows({ ...EMPTY, allowed_domains: [{ domain: "nsight.fi", mode: "edit" }] }))
      .toEqual([{ domain: "nsight.fi", signIn: true, mode: "edit" }]);
  });

  it("has no rows when nothing is configured", () => {
    expect(toRows(undefined)).toEqual([]);
  });
});

describe("toStored", () => {
  it("writes the two controls to the two lists", () => {
    expect(toStored([{ domain: "nsight.fi", signIn: true, mode: "edit" }])).toEqual({
      allowed_domains: ["nsight.fi"],
      domain_access: [{ domain: "nsight.fi", mode: "edit" }],
    });
  });

  it("writes sign-in alone when no access was chosen", () => {
    expect(toStored([{ domain: "nsight.fi", signIn: true, mode: "none" }])).toEqual({
      allowed_domains: ["nsight.fi"],
      domain_access: [],
    });
  });

  it("writes access alone when sign-in is off", () => {
    expect(toStored([{ domain: "partner.com", signIn: false, mode: "view" }])).toEqual({
      allowed_domains: [],
      domain_access: [{ domain: "partner.com", mode: "view" }],
    });
  });

  it("never writes a mode into the sign-in list", () => {
    // That shape is read for compatibility, but writing it back would put the
    // two questions in one field again -- which is the thing being undone.
    const out = toStored([{ domain: "nsight.fi", signIn: true, mode: "edit" }]);
    expect(out.allowed_domains.every((d) => typeof d === "string")).toBe(true);
  });

  it("drops a row that is neither admitted nor granted", () => {
    expect(toStored([{ domain: "x.fi", signIn: false, mode: "none" }])).toEqual({
      allowed_domains: [], domain_access: [],
    });
  });

  it("trims and lowercases what was typed", () => {
    expect(toStored([{ domain: "  NSight.FI ", signIn: true, mode: "view" }])).toEqual({
      allowed_domains: ["nsight.fi"],
      domain_access: [{ domain: "nsight.fi", mode: "view" }],
    });
  });

  it("drops a row whose domain was left blank", () => {
    expect(toStored([{ domain: "  ", signIn: true, mode: "view" }])).toEqual({
      allowed_domains: [], domain_access: [],
    });
  });

  it("round-trips a saved setting, so an untouched screen is not dirty", () => {
    const saved = {
      ...EMPTY,
      allowed_domains: ["nsight.fi"],
      domain_access: [{ domain: "partner.com", mode: "view" as const }],
    };
    const out = toStored(toRows(saved));
    expect(out.allowed_domains).toEqual(saved.allowed_domains);
    expect(out.domain_access).toEqual(saved.domain_access);
  });
});

// The endpoint REPLACES the stored setting, so the body has to be whole every
// time: a list left out is a list emptied. `saveBody` is the one place it is
// built, which is what stops a caller sending half of what the screen knows.
describe("saveBody", () => {
  it("sends both lists and the grants the screen does not edit", () => {
    const current = {
      allowed_domains: ["old.fi"],
      domain_access: [{ domain: "old.fi", mode: "view" as const }],
      default_grants: [{ scope: "cust-1", mode: "edit" }],
    };
    expect(saveBody([{ domain: "nsight.fi", signIn: true, mode: "edit" }], current))
      .toEqual({
        allowed_domains: ["nsight.fi"],
        domain_access: [{ domain: "nsight.fi", mode: "edit" }],
        default_grants: [{ scope: "cust-1", mode: "edit" }],
      });
  });

  it("still names both lists when the screen has no rows", () => {
    // Not an omission — "I looked, there are none" — and the shape must say so
    // rather than leave the key out.
    expect(saveBody([], EMPTY)).toEqual({
      allowed_domains: [], domain_access: [], default_grants: [],
    });
  });

  it("carries no grants when the server had none", () => {
    expect(saveBody([{ domain: "a.fi", signIn: false, mode: "view" }], undefined))
      .toEqual({
        allowed_domains: [],
        domain_access: [{ domain: "a.fi", mode: "view" }],
        default_grants: [],
      });
  });

  it("never invents a grant list of its own", () => {
    const out = saveBody([], { ...EMPTY, default_grants: [] });
    expect(out.default_grants).toEqual([]);
  });
});
