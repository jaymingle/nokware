import { formatDate } from "@/lib/time";

import type { PetitionDetail } from "@/lib/api/types";

/**
 * What the departments the MCE asked have said. Under the department's name, never the officer's: the Assembly
 * answers as the Assembly. A department asked but silent is shown too — that it was asked is the public part.
 */
export function DepartmentNotes({ petition }: { petition: PetitionDetail }) {
  // Absent on a petition read before this existed, as on one nobody has been asked about.
  const shares = petition.shared_with ?? [];
  if (shares.length === 0) return null;
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="petition-departments">
      <h2 className="text-[19px]">What the departments say</h2>
      {shares.map((share) => (
        <div key={share.department} className="flex flex-col gap-1.5 border-b pb-3 last:border-0 last:pb-0"
          data-testid={`petition-department-${share.department}`}>
          <p className="text-[15px] font-medium">{share.department}</p>
          {share.note
            ? <p className="text-[15px] whitespace-pre-line" data-testid="petition-department-note">{share.note}</p>
            : <p className="text-[14px] text-ink-soft">Asked to answer. Nothing written yet.</p>}
          <p className="text-[13px] text-ink-soft">
            Asked on {formatDate(share.shared_at)}{share.note_at ? ` · answered on ${formatDate(share.note_at)}` : ""}
          </p>
        </div>
      ))}
    </section>
  );
}
