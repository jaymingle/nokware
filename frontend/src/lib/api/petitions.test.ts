import { beforeEach, describe, expect, it, vi } from "vitest";

import { addPetitionComment, getPetitionComments, replyToResponse, reportPetitionComment } from "@/lib/api/petitions";

const api = vi.hoisted(() => ({ publicRequest: vi.fn(), postJson: vi.fn(), postWithProgress: vi.fn() }));

// The API's own door is stubbed: these are the paths, bodies and headers each call goes out with.
vi.mock("@/lib/api/public", () => ({ publicRequest: api.publicRequest, postJson: api.postJson }));
vi.mock("@/lib/api/upload", () => ({ postWithProgress: api.postWithProgress }));

describe("the comments under a petition", () => {
  beforeEach(() => {
    api.publicRequest.mockReset().mockResolvedValue({ comments: [], total: 0 });
    api.postJson.mockReset().mockResolvedValue({});
  });

  it("reads them a page at a time", async () => {
    await getPetitionComments("504162", 20, 40);
    expect(api.publicRequest).toHaveBeenCalledWith("/api/petitions/504162/comments?limit=20&offset=40");
  });

  it("sends a comment with the proof of a confirmed number, and nothing else of the writer", async () => {
    await addPetitionComment("504162", { text: "The drain floods every year.", name: "Ama" }, "proof-token");
    expect(api.postJson).toHaveBeenCalledWith("/api/petitions/504162/comments",
      { text: "The drain floods every year.", name: "Ama" }, { "X-Phone-Proof": "proof-token" });
  });

  it("leaves the name out, for a comment that stands as Resident", async () => {
    await addPetitionComment("504162", { text: "Same here.", name: null }, "proof-token");
    expect(api.postJson).toHaveBeenCalledWith("/api/petitions/504162/comments", { text: "Same here.", name: null },
      { "X-Phone-Proof": "proof-token" });
  });

  it("reports one without signing in: no proof goes with the report", async () => {
    await reportPetitionComment("504162", "68c1f0a2", { ground: "private_individual", note: "Names a neighbour." });
    expect(api.postJson).toHaveBeenCalledWith("/api/petitions/504162/comments/68c1f0a2/report",
      { ground: "private_individual", note: "Names a neighbour." });
  });

  it("keeps an odd comment id inside its own part of the path", async () => {
    await reportPetitionComment("504162", "a/b c", { ground: "duplicate", note: null });
    expect(api.postJson).toHaveBeenCalledWith("/api/petitions/504162/comments/a%2Fb%20c/report",
      { ground: "duplicate", note: null });
  });
});

describe("the petitioner's reply to the response", () => {
  beforeEach(() => {
    api.postJson.mockReset().mockResolvedValue({ state: "published" });
  });

  it("goes out on the number the petition was started with", async () => {
    await replyToResponse("504162", "The work stopped in March.", "proof-token");
    expect(api.postJson).toHaveBeenCalledWith("/api/petitions/504162/reply", { text: "The work stopped in March." },
      { "X-Phone-Proof": "proof-token" });
  });

  it("answers with the petition as it now reads, so the page can show the reply", async () => {
    expect(await replyToResponse("504162", "Thank you.", "proof-token")).toEqual({ state: "published" });
  });
});
