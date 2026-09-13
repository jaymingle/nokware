import { describe, expect, it } from "vitest";

import { describeProvenance, groupSources, linkCitations } from "@/lib/ask/sources";

import type { AskSource } from "@/lib/api/types";

function chunk(label: string, text: string, fields: Partial<AskSource> = {}): AskSource {
  return {
    label,
    cited: false,
    document_id: `doc-${label}`,
    title: `Title ${label}`,
    chunk_text: text,
    department: "dept-finance",
    department_name: "Finance",
    source_type: "agency",
    provenance: "ama_website",
    source_url: "https://ama.gov.gh/documents/x.pdf",
    published_at: "2026-09-12T10:00:00+00:00",
    document_year: 2024,
    ...fields,
  };
}

describe("groupSources", () => {
  it("gives each document one entry, in label order, with all its excerpts", () => {
    const docs = groupSources([chunk("S1", "a"), chunk("S1", "b"), chunk("S2", "c")]);
    expect(docs.map((doc) => [doc.label, doc.excerpts])).toEqual([["S1", ["a", "b"]], ["S2", ["c"]]]);
  });
});

describe("describeProvenance", () => {
  const url = "https://www.example.org/report.pdf";

  it("says an imported document was published on ama.gov.gh, linking the original", () => {
    const view = describeProvenance({ provenance: "ama_website", departmentName: "Finance", sourceUrl: "https://ama.gov.gh/d.pdf" });
    expect(view).toEqual({ text: "Published by Finance on", link: { text: "ama.gov.gh", href: "https://ama.gov.gh/d.pdf" }, joiner: " " });
  });

  it("says a portal upload was submitted by the department", () => {
    expect(describeProvenance({ provenance: "department_portal", departmentName: "Finance", sourceUrl: null })).toEqual({
      text: "Submitted by Finance",
      link: null,
      joiner: " · ",
    });
  });

  it("names a contributor's source by its site", () => {
    const view = describeProvenance({ provenance: "contributor", departmentName: "Works", sourceUrl: url });
    expect(view?.text).toBe("Verified contributor — sourced from");
    expect(view?.link).toEqual({ text: "example.org", href: url });
  });

  it("says nothing rather than guess when the record doesn't say", () => {
    expect(describeProvenance({ provenance: null, departmentName: "Finance", sourceUrl: url })).toBeNull();
  });
});

describe("linkCitations", () => {
  it("turns each label into a citation link, including adjacent ones", () => {
    expect(linkCitations("Fees rose [S1][S3].")).toBe("Fees rose [S1](#cite-S1)[S3](#cite-S3).");
  });
});
