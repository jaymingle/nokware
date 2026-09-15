import { describe, expect, it } from "vitest";

import { joinNames, lowerFirst } from "@/lib/text";

describe("joinNames", () => {
  it("joins names as a sentence would", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["Works"])).toBe("Works");
    expect(joinNames(["Ghana Police Service", "Social Welfare"])).toBe("Ghana Police Service and Social Welfare");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
  });
});

describe("a label inside a sentence", () => {
  it("lower-cases only its first letter, so the Assembly keeps its capital", () => {
    expect(lowerFirst("Not the Assembly's responsibility")).toBe("not the Assembly's responsibility");
    expect(lowerFirst("")).toBe("");
  });
});
