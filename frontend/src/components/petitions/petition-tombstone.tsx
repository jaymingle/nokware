import Link from "next/link";

import { PageShell } from "@/components/page-shell";
import { StatusTag } from "@/components/status-tag";
import { previousRemovalsLine, removedLine, spacedCode } from "@/lib/petitions";
import { petitionStatus } from "@/lib/status";

import type { PetitionTombstone } from "@/lib/api/types";

/**
 * All that is left of a removed petition. The API builds this from the removal record alone, so there is no
 * title, no words, no photo, no signature count and no answer to leave out — and nothing here goes looking for
 * any. The page says what came down, when, and on what ground, because a removal that left no trace would be a
 * quieter kind of deletion.
 */
export function PetitionTombstoneView({ stone }: { stone: PetitionTombstone }) {
  const tag = petitionStatus("removed");
  const previous = previousRemovalsLine(stone.previous_removals);
  return (
    <PageShell eyebrow="Petitions" title={`Petition ${spacedCode(stone.code)}`}>
      <div className="flex flex-col gap-4 rounded-xl border bg-card p-5" data-testid="petition-tombstone">
        <div><StatusTag tone={tag.tone} testId="petition-status">{tag.label}</StatusTag></div>
        <p className="text-[15px]" data-testid="petition-tombstone-ground">{removedLine(stone)}</p>
        {stone.duplicate_of ? (
          <p className="text-[14px]" data-testid="petition-tombstone-duplicate">
            The petition it duplicated:{" "}
            <Link href={`/petitions/${stone.duplicate_of}`} className="underline underline-offset-2" data-testid="petition-tombstone-duplicate-link">
              {spacedCode(stone.duplicate_of)}
            </Link>
          </p>
        ) : null}
        {previous ? <p className="text-[13.5px] text-ink-soft" data-testid="petition-tombstone-previous">{previous}</p> : null}
        <p className="text-[13px] text-ink-soft">
          A contributor took it down on a named ground. The person who started it can mend the words and publish it
          again, at this same number.
        </p>
      </div>
    </PageShell>
  );
}
