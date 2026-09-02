/**
 * What an author reads when the server refuses their upload.
 *
 * The server explains itself in `detail`; the dialog shows `error.message`
 * verbatim. Passing the raw body through put a line of JSON in front of the
 * author — "422 Unprocessable Entity: {"detail":"…"}" — which buries the one
 * sentence written for them.
 */
import { describe, expect, it } from "vitest";
import { errorMessage } from "./apiError";

describe("errorMessage", () => {
  it("shows the server's explanation on its own", () => {
    expect(errorMessage(422, "Unprocessable Entity",
      JSON.stringify({ detail: "notes.sav could not be read as an SPSS .sav file." }))
    ).toBe("notes.sav could not be read as an SPSS .sav file.");
  });

  it("falls back to status and body when there is no detail", () => {
    expect(errorMessage(500, "Internal Server Error", "boom"))
      .toBe("500 Internal Server Error: boom");
  });

  it("falls back when the body is not JSON", () => {
    expect(errorMessage(502, "Bad Gateway", "<html>nginx</html>"))
      .toBe("502 Bad Gateway: <html>nginx</html>");
  });

  it("keeps FastAPI's validation-error shape readable rather than [object Object]", () => {
    const body = JSON.stringify({ detail: [{ loc: ["body", "file"], msg: "Field required" }] });
    expect(errorMessage(422, "Unprocessable Entity", body)).toBe("Field required");
  });
});
