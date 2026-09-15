import { afterEach, describe, expect, it, vi } from "vitest";

import { checkKey, EMPTY_DRAFT, toRequest } from "@/hooks/use-petition-draft";
import {
  closingLine,
  keepProof,
  keptProof,
  placeLine,
  progressPercent,
  publishedLine,
  signaturesLine,
  spacedCode,
  startedBy,
  timelineText,
  whatsappShareUrl,
} from "@/lib/petitions";

const NOW = Date.parse("2026-09-15T09:00:00Z");

describe("how a petition reads in public", () => {
  it("says who published it: the MCE, or the clock the MCE let run out", () => {
    expect(publishedLine({ published_at: "2026-09-12T09:00:00Z", published_by: "mce" })).toBe("Published by the MCE on 12 Sept 2026");
    expect(publishedLine({ published_at: "2026-09-12T09:00:00Z", published_by: "automatic" })).toBe(
      "Published automatically on 12 Sept 2026: the MCE didn't decide within 72 hours");
    expect(publishedLine({ published_at: null, published_by: null })).toBeNull();
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
    expect(closingLine({ ...open, status: "withdrawn", closed_at: "2026-10-01T09:00:00Z" }, NOW)).toBe(
      "Withdrawn by the person who started it on 1 Oct 2026");
  });

  it("gives a refusal's reason in the timeline, and shares the ask with the link", () => {
    expect(timelineText({ action: "refused", at: "t", reason: "Names a private individual" })).toBe("Refused by the MCE: Names a private individual");
    expect(timelineText({ action: "auto_published", at: "t", reason: null })).toContain("didn't decide within 72 hours");
    expect(decodeURIComponent(whatsappShareUrl("Desilt the drain", "https://nokware.org/petitions/482913"))).toContain(
      "Petition to the Accra Metropolitan Assembly: Desilt the drain\nhttps://nokware.org/petitions/482913");
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
