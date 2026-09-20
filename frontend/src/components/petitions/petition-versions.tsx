import { earlierVersionsLine, versionChanges } from "@/lib/petitions";
import { formatDate } from "@/lib/time";

import type { PetitionVersion } from "@/lib/api/types";

/**
 * Every wording this petition has had, oldest first. Signatures belong to the petition rather than to one version
 * of it, so where some were given before the words last changed, the page says how many: a reader comparing the
 * number with what is in front of them should not have to guess.
 */
export function PetitionVersions({ versions, onEarlier }: { versions: PetitionVersion[]; onEarlier: number }) {
  const earlier = earlierVersionsLine(onEarlier);
  if (versions.length < 2 && !earlier) return null;
  return (
    <ol className="flex flex-col gap-2 text-[13.5px]" data-testid="petition-versions">
      {versions.map((entry) => (
        <li key={entry.version} className="flex flex-wrap items-baseline gap-x-3" data-testid={`petition-version-${entry.version}`}>
          <span className="w-28 shrink-0 text-ink-soft tabular-nums">{formatDate(entry.at)}</span>
          <span>
            <span className="tabular-nums">Version {entry.version}</span>
            <span className="text-ink-soft"> · {versionChanges(entry.changed)}</span>
          </span>
        </li>
      ))}
      {earlier ? (
        <li className="pt-1 text-ink-soft" data-testid="petition-versions-earlier">
          {earlier}: signed before the words were last edited. They still count.
        </li>
      ) : null}
    </ol>
  );
}
