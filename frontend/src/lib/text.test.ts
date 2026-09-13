import { describe, expect, it } from "vitest";

import { joinNames } from "@/lib/text";

describe("joinNames", () => {
  it("joins names as a sentence would", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["Works"])).toBe("Works");
    expect(joinNames(["Ghana Police Service", "Social Welfare"])).toBe("Ghana Police Service and Social Welfare");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
  });
});
