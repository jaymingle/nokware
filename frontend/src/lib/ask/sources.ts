import type { AskSource, Provenance } from "@/lib/api/types";

/** One cited document: the answer's [S#] label and everything shown on its card. */
export type SourceDocument = {
  label: string;
  documentId: string;
  title: string;
  departmentName: string | null;
  provenance: Provenance | null;
  sourceUrl: string | null;
  documentYear: number | null;
  publishedAt: string | null;
  cited: boolean;
  excerpts: string[];
};

/** The API sends one entry per retrieved chunk; a document's chunks share a label. */
export function groupSources(sources: AskSource[]): SourceDocument[] {
  const documents = new Map<string, SourceDocument>();
  for (const source of sources) {
    const existing = documents.get(source.label);
    if (existing) {
      existing.excerpts.push(source.chunk_text);
      continue;
    }
    documents.set(source.label, {
      label: source.label,
      documentId: source.document_id,
      title: source.title ?? "Untitled document",
      departmentName: source.department_name,
      provenance: source.provenance,
      sourceUrl: source.source_url,
      documentYear: source.document_year,
      publishedAt: source.published_at,
      cited: source.cited,
      excerpts: [source.chunk_text],
    });
  }
  return [...documents.values()];
}

/** Marks the documents the final answer cites. */
export function markCited(documents: SourceDocument[], cited: string[]): SourceDocument[] {
  const labels = new Set(cited);
  return documents.map((doc) => ({ ...doc, cited: labels.has(doc.label) }));
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** A provenance statement with an optional link after it, e.g. "Published by Finance on" + "ama.gov.gh". */
export type ProvenanceView = { text: string; link: { text: string; href: string } | null; joiner: string };

/**
 * Where the document came from, stated precisely for each way into the Ledger:
 * imported from ama.gov.gh, submitted through the portal by a department, or
 * from a verified contributor. Returns null when the record doesn't say.
 */
export function describeProvenance(doc: Pick<SourceDocument, "provenance" | "departmentName" | "sourceUrl">): ProvenanceView | null {
  const department = doc.departmentName ?? "the Assembly";
  const url = doc.sourceUrl;
  if (doc.provenance === "ama_website") {
    return url
      ? { text: `Published by ${department} on`, link: { text: "ama.gov.gh", href: url }, joiner: " " }
      : { text: `Published by ${department} on ama.gov.gh`, link: null, joiner: "" };
  }
  if (doc.provenance === "department_portal") {
    return { text: `Submitted by ${department}`, link: url ? { text: `Source: ${hostOf(url)}`, href: url } : null, joiner: " · " };
  }
  if (doc.provenance === "contributor") {
    return url
      ? { text: "Verified contributor — sourced from", link: { text: hostOf(url), href: url }, joiner: " " }
      : { text: "Verified contributor", link: null, joiner: "" };
  }
  return null;
}

// S: a document; R: a live report count; B: an amount read from a budget. B was
// missing here while budget figures were being cited, so every budget answer
// showed "[B1]" as bare text where its citation should have been.
const CITATION = /\[([SRB]\d+)\]/g;
export const CITATION_HREF_PREFIX = "#cite-";

/** Turns each [S1], [R1] or [B1] into a markdown link the renderer shows as a citation tag. */
export function linkCitations(markdown: string): string {
  return markdown.replace(CITATION, (_, label: string) => `[${label}](${CITATION_HREF_PREFIX}${label})`);
}

/** The fixed wording the backend tells the model to use when sources conflict. */
export const DISAGREEMENT_LEAD = "The sources disagree";
