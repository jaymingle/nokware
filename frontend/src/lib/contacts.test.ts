import { describe, expect, it } from "vitest";

import { numberHref, tierNote } from "@/lib/contacts";

import type { PublicContact } from "@/lib/api/types";

const contact = (fields: Partial<PublicContact>): PublicContact => ({
  id: "x", service: "police", tier: 2, name: "Line", numbers: [], ...fields,
});

describe("numberHref", () => {
  it("dials calls as written and opens WhatsApp in international form", () => {
    expect(numberHref({ number: "112", kind: "call" })).toBe("tel:112");
    expect(numberHref({ number: "0302 665 951", kind: "call" })).toBe("tel:0302665951");
    expect(numberHref({ number: "0204 833 556", kind: "whatsapp" })).toBe("https://wa.me/233204833556");
  });
});

describe("tierNote", () => {
  it("says how far each number can be trusted", () => {
    expect(tierNote(contact({ tier: 1 }))).toBe("National emergency line");
    expect(tierNote(contact({ tier: 3, reported_via: "Facebook", reported_by: "the Mayor of Accra" }))).toBe(
      "Reported via Facebook by the Mayor of Accra, not independently verified",
    );
    expect(tierNote(contact({ tier: 3 }))).toBe("Reported on social media, not independently verified");
  });
});
