import { describe, expect, it, vi } from "vitest";

import { MAX_EDGE, fitInside, shrink } from "@/lib/report/shrink";

const photo = (name = "drain.jpg", type = "image/jpeg") => new File([new Uint8Array(1)], name, { type, lastModified: 1 });

describe("a photo is shrunk before it is sent", () => {
  it("fits inside the long edge the API stores, and never enlarges a small photo", () => {
    expect(fitInside(4032, 3024)).toEqual({ width: MAX_EDGE, height: 1536 });
    expect(fitInside(3024, 4032)).toEqual({ width: 1536, height: MAX_EDGE });
    expect(fitInside(800, 600)).toEqual({ width: 800, height: 600 });
    expect(fitInside(1, 1)).toEqual({ width: 1, height: 1 });
  });

  it("sends the photo as it is when the browser can't read it", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("not an image")));
    const chosen = photo();
    await expect(shrink(chosen)).resolves.toBe(chosen); // the API decides, with its own message
    vi.unstubAllGlobals();
  });

  it("leaves a file the API wouldn't accept alone", async () => {
    const chosen = photo("notes.pdf", "application/pdf");
    await expect(shrink(chosen)).resolves.toBe(chosen);
  });
});
