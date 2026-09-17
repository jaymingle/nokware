import { DocumentLine } from "@/components/petitions/ledger-matches";
import { respondedLine } from "@/lib/petitions";

import type { PetitionDetail } from "@/lib/api/types";

export function MceResponse({ petition }: { petition: PetitionDetail }) {
  const response = petition.response;
  if (!response) return null;
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-teal bg-card p-5" data-testid="petition-response">
      <h2 className="text-[19px]">The MCE&apos;s response</h2>
      <p className="text-[15px] font-medium" data-testid="petition-response-kind">
        {response.label}{response.department ? `: ${response.department}` : ""}
      </p>
      <p className="text-[15px] whitespace-pre-line" data-testid="petition-response-text">{response.text}</p>
      {response.documents.length > 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-[13px] text-ink-soft">Documents the MCE cites</p>
          {response.documents.map((doc) => <DocumentLine key={doc.id} doc={doc} />)}
        </div>
      ) : null}
      <p className="text-[13px] text-ink-soft" data-testid="petition-response-when">{respondedLine({ responded_at: response.responded_at, response_due: petition.response_due })}</p>
    </section>
  );
}
