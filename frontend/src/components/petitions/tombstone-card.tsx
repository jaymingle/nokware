import Link from "next/link";

import { StatusTag } from "@/components/status-tag";
import { previousRemovalsLine, removedLine, spacedCode } from "@/lib/petitions";
import { petitionStatus } from "@/lib/status";

import type { PetitionTombstone } from "@/lib/api/types";

/**
 * One line of the removed list. It is built from the same tombstone the petition's own page shows, so a list of a
 * hundred can say no more about a petition than opening one of them does: a number, a date, a ground.
 */
export function TombstoneCard({ stone }: { stone: PetitionTombstone }) {
  const tag = petitionStatus("removed");
  const previous = previousRemovalsLine(stone.previous_removals);
  return (
    <li className="flex flex-col gap-2 border-b py-4 last:border-0" data-testid={`tombstone-${stone.code}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={`/petitions/${stone.code}`} className="text-[16px] font-medium underline underline-offset-2"
          data-testid={`tombstone-${stone.code}-link`}>
          Petition {spacedCode(stone.code)}
        </Link>
        <StatusTag tone={tag.tone} testId={`tombstone-${stone.code}-status`}>{tag.label}</StatusTag>
      </div>
      <p className="text-[14px]" data-testid={`tombstone-${stone.code}-ground`}>{removedLine(stone)}</p>
      {stone.duplicate_of ? (
        <p className="text-[12.5px] text-ink-soft">
          The petition it duplicated:{" "}
          <Link href={`/petitions/${stone.duplicate_of}`} className="underline underline-offset-2"
            data-testid={`tombstone-${stone.code}-duplicate`}>
            {spacedCode(stone.duplicate_of)}
          </Link>
        </p>
      ) : null}
      {previous ? <p className="text-[12.5px] text-ink-soft">{previous}</p> : null}
    </li>
  );
}
