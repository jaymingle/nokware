import { afterEach, describe, expect, it, vi } from "vitest";

import { checkKey, EMPTY_DRAFT, toRequest } from "@/hooks/use-petition-draft";
import {
  closingLine,
  earlierVersionsLine,
  keepProof,
  nameNote,
  NO_RESPONSE,
  previousRemovalsLine,
  removedBeforeLine,
  removedLine,
  responseLine,
  keptProof,
  placeLine,
  progressPercent,
  publishedLine,
  sendingLabel,
  signaturesLine,
  spacedCode,
  startedBy,
  timelineText,
  versionChanges,
  whatsappShareUrl,
} from "@/lib/petitions";

const NOW = Date.parse("2026-09-15T09:00:00Z");

describe("how a petition reads in public", () => {
  it("says when it was published, and nothing about anyone approving it", () => {
    expect(publishedLine({ published_at: "2026-09-12T09:00:00Z" })).toBe("Published on 12 Sept 2026");
    expect(publishedLine({ published_at: null })).toBeNull();
  });

  it("names the creator only when they chose to be named", () => {
    expect([startedBy(null), startedBy("Ama Mensah")]).toEqual(["Started by a resident", "Started by Ama Mensah"]);
  });

  it("gives the place, the number and the support in plain words", () => {
    expect(placeLine({ scope: "area", area: "Kaneshie", sub_metro: "Okaikoi South" })).toBe("Kaneshie, Okaikoi South");
    expect(placeLine({ scope: "metro", area: null, sub_metro: null })).toBe("The whole Assembly");
    expect(spacedCode("482913")).toBe("482 913");
    expect([signaturesLine(1, 150), signaturesLine(1200, 500)]).toEqual(["1 signature of 150", "1,200 signatures of 500"]);
    expect([progressPercent(75, 150), progressPercent(900, 500), progressPercent(3, null)]).toEqual([50, 100, 0]);
  });

  it("says how long it stays open, or when and why it closed", () => {
    const open = { status: "open" as const, closes_at: "2026-12-14T09:00:00Z", closed_at: null, threshold: 150 };
    expect(closingLine(open, NOW)).toBe("Open until 14 Dec 2026 (90 days left)");
    expect(closingLine({ ...open, status: "closed", closed_at: "2026-12-14T09:00:00Z" }, NOW)).toBe(
      "Closed on 14 Dec 2026. It didn't reach 150 signatures in 90 days.");
  });

  it("gives a removal's ground in the timeline, and shares the ask with the link", () => {
    expect(timelineText({ action: "removed", at: "t", reason: "Contains personal data" })).toBe("Removed: Contains personal data");
    expect(timelineText({ action: "republished", at: "t", reason: null })).toBe("Edited and published again");
    expect(timelineText({ action: "published", at: "t", reason: null })).toBe("Published by the person who started it");
    expect(decodeURIComponent(whatsappShareUrl("Desilt the drain", "https://nokware.tstitagency.com/petitions/482913"))).toContain(
      "Petition to the Accra Metropolitan Assembly: Desilt the drain\nhttps://nokware.tstitagency.com/petitions/482913");
  });

  it("names the department in the line rather than hanging it off a label", () => {
    expect(timelineText({ action: "shared", at: "t", reason: "Works Department" })).toBe(
      "Sent to Works Department for its answer");
    expect(timelineText({ action: "department_note", at: "t", reason: "Works Department" })).toBe(
      "Works Department answered");
  });
});

describe("a petition that was edited, or taken down", () => {
  it("says which words a version changed, in the reader's terms and not the database's", () => {
    expect(versionChanges([])).toBe("First version");
    expect(versionChanges(["body"])).toBe("Changed the reasons");
    expect(versionChanges(["title", "wardLocation", "imageIds"])).toBe("Changed the ask, the electoral area and the photos");
    // A field this build has never met is left out rather than printed as a column name.
    expect(versionChanges(["body", "somethingNew"])).toBe("Changed the reasons");
  });

  it("counts the signatures given before the words last changed, and says nothing when there are none", () => {
    expect(earlierVersionsLine(0)).toBeNull();
    expect(earlierVersionsLine(1)).toBe("1 on an earlier version");
    expect(earlierVersionsLine(1200)).toBe("1,200 on an earlier version");
  });

  it("says plainly how many times it came down, on the petition and on the tombstone", () => {
    expect(removedBeforeLine(0)).toBeNull();
    expect(removedBeforeLine(1)).toBe("This petition has been removed once and published again.");
    expect(removedBeforeLine(3)).toBe("This petition has been removed 3 times and published again.");
    expect(previousRemovalsLine(0)).toBeNull();
    expect(previousRemovalsLine(2)).toBe("It had been removed twice before this.");
    expect(previousRemovalsLine(3)).toBe("It had been removed 3 times before this.");
    expect(removedLine({ ground_words: "Contains personal data", removed_at: "2026-09-12T09:00:00Z" })).toBe(
      "Removed on 12 Sept 2026: contains personal data.");
  });

  it("says how far the photos have gone while they are going", () => {
    expect(sendingLabel({ sent: 512, total: 2048 })).toBe("Sending your photos… 25%");
    expect(sendingLabel("filing")).toBe("Publishing…");
    expect(sendingLabel(null, "Saving…")).toBe("Saving…");
  });
});

describe("once a petition reaches its signatures", () => {
  const reached = {
    status: "awaiting_response" as const, threshold: 150, closes_at: "2026-12-14T09:00:00Z", closed_at: null,
    threshold_reached_at: "2026-09-15T09:00:00Z", response_due: "2026-10-15T09:00:00Z", responded_at: null, unanswered_at: null,
  };

  it("counts down the MCE's 30 days, then says plainly that there was no response", () => {
    expect(responseLine(reached, NOW)).toBe(
      "Reached 150 signatures on 15 Sept 2026. The MCE has until 15 Oct 2026 to respond publicly on this page: 30 days left.");
    expect(responseLine(reached, Date.parse("2026-10-15T09:00:00Z"))).toBe(`Reached 150 signatures on 15 Sept 2026. ${NO_RESPONSE}`);
    expect(NO_RESPONSE).toBe("No response 30 days after the petition reached its threshold.");
    expect(responseLine({ ...reached, status: "open" }, NOW)).toBeNull();
  });

  it("says once recorded that there was no response, and a late answer says how late it came", () => {
    expect(responseLine({ ...reached, unanswered_at: "2026-10-15T09:02:00Z" }, NOW)).toContain(NO_RESPONSE);
    const answered = { ...reached, status: "responded" as const };
    expect(responseLine({ ...answered, responded_at: "2026-10-01T10:00:00Z" }, NOW)).toBe("The MCE responded on 1 Oct 2026.");
    expect(responseLine({ ...answered, responded_at: "2026-10-17T09:09:00Z" }, NOW)).toBe(
      "The MCE responded on 17 Oct 2026, 2 days after the 30-day deadline."); // 2 days 9 minutes: never rounded up
    expect(responseLine({ ...answered, responded_at: "2026-10-15T14:00:00Z" }, NOW)).toBe(
      "The MCE responded on 15 Oct 2026, less than a day after the 30-day deadline.");
    expect(closingLine(answered, NOW)).toBe("It takes no more signatures: the MCE has responded.");
    expect(timelineText({ action: "no_response", at: "t", reason: null })).toBe(NO_RESPONSE.replace(/\.$/, ""));
  });

  it("keeps taking signatures until its 90 days are up", () => {
    expect(closingLine(reached, NOW)).toBe("Signing stays open until 14 Dec 2026");
    expect(closingLine(reached, Date.parse("2026-12-15T00:00:00Z"))).toBe("Signing has closed");
    expect(timelineText({ action: "threshold_reached", at: "t", reason: null })).toBe("Reached its signatures and went to the MCE for a response");
  });

  it("tells a signer exactly who can see a public name", () => {
    expect(nameNote("Works Department")).toContain("including Works Department, which it concerns");
    expect(nameNote(null)).toContain("including the department it concerns");
  });
});

describe("what this browser keeps", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps a confirmed phone in the tab until it expires", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("sessionStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v), removeItem: (k: string) => store.delete(k) });
    keepProof({ token: "t", number: "+233…67", expiresAt: "2026-09-15T21:00:00Z" });
    expect(keptProof(NOW)?.number).toBe("+233…67");
    expect(keptProof(Date.parse("2026-09-15T21:00:00Z"))).toBeNull();
    keepProof(null);
    expect(keptProof(NOW)).toBeNull();
  });

  it("works without storage, as in a private window", () => {
    expect(keptProof(NOW)).toBeNull();
  });

  it("sends only the area an area petition needs, and checks again when the words change", () => {
    const draft = { ...EMPTY_DRAFT, title: "Desilt the drain", body: "It floods.", topic: "drainage", scope: "metro" as const, ward: "kaneshie" };
    expect(toRequest(draft).ward).toBeNull();
    expect(toRequest({ ...draft, scope: "area" }).ward).toBe("kaneshie");
    expect(checkKey(draft)).toBe(checkKey({ ...draft, title: " Desilt the drain ", ward: "" }));
    expect(checkKey(draft)).not.toBe(checkKey({ ...draft, body: "It floods every June." }));
  });
});
