"use client";

import { ErrorNote } from "@/components/documents/panels";
import { Progress } from "@/components/petitions/petition-card";
import { PetitionTimeline } from "@/components/petitions/petition-timeline";
import { PetitionVersions } from "@/components/petitions/petition-versions";
import { useMyPetition } from "@/lib/api/petition-queries";
import { earlierVersionsLine, respondedLine } from "@/lib/petitions";
import { formatDate } from "@/lib/time";

import type { OwnPetitionDetail } from "@/lib/api/types";

function Block({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <div className="flex flex-col gap-2 border-t pt-4" data-testid={testId}>
      <h3 className="text-[14px] font-medium">{title}</h3>
      {children}
    </div>
  );
}

function Response({ petition }: { petition: OwnPetitionDetail }) {
  const response = petition.response;
  if (!response) return null;
  return (
    <Block title="The MCE's response" testId={`own-${petition.code}-response`}>
      <p className="text-[13.5px] font-medium">{response.label}</p>
      <p className="text-[13.5px] whitespace-pre-line">{response.text}</p>
      <p className="text-[12.5px] text-ink-soft">
        {respondedLine({ responded_at: response.responded_at, response_due: petition.response_due })}
      </p>
      {response.reply ? (
        <p className="rounded-lg bg-paper-subtle px-3 py-2 text-[13px]" data-testid={`own-${petition.code}-reply`}>
          You replied on {formatDate(response.reply.at)}: {response.reply.text}
        </p>
      ) : (
        <p className="text-[12.5px] text-ink-soft">You can reply to this once, on the petition&apos;s own page.</p>
      )}
    </Block>
  );
}

function Departments({ petition }: { petition: OwnPetitionDetail }) {
  if (petition.shared_with.length === 0) return null;
  return (
    <Block title="Departments asked to answer" testId={`own-${petition.code}-departments`}>
      {petition.shared_with.map((share) => (
        <div key={share.department} className="flex flex-col gap-1">
          <p className="text-[13.5px] font-medium">{share.department}</p>
          {share.note
            ? <p className="text-[13.5px] whitespace-pre-line">{share.note}</p>
            : <p className="text-[13px] text-ink-soft">Asked to answer. Nothing written yet.</p>}
          <p className="text-[12.5px] text-ink-soft">
            Asked on {formatDate(share.shared_at)}{share.note_at ? ` · answered on ${formatDate(share.note_at)}` : ""}
          </p>
        </div>
      ))}
    </Block>
  );
}

/**
 * Everything the public page says about a petition, for the one person the public page can't tell: the creator of
 * a removed one, whose page is a tombstone. Read per card, by its number and the number that started it.
 */
export function OwnPetitionRecord({ code, proof }: { code: string; proof: string }) {
  const { data: petition, error } = useMyPetition(code, proof);
  if (error) return <ErrorNote testId={`own-${code}-record-error`}>{error.message}</ErrorNote>;
  if (!petition) return null;
  const earlier = earlierVersionsLine(petition.signatures_on_earlier_versions);
  return (
    <div className="flex flex-col gap-4" data-testid={`own-${code}-record`}>
      <div className="flex flex-col gap-1 border-t pt-4">
        <div className="max-w-sm"><Progress signatures={petition.signatures} threshold={petition.threshold} /></div>
        {earlier ? <p className="text-[12.5px] text-ink-soft">{earlier}</p> : null}
      </div>
      <Response petition={petition} />
      <Departments petition={petition} />
      {petition.versions.length > 1 ? (
        <Block title="How your words have changed" testId={`own-${code}-versions`}>
          <PetitionVersions versions={petition.versions} onEarlier={petition.signatures_on_earlier_versions} />
        </Block>
      ) : null}
      <Block title="What has happened" testId={`own-${code}-timeline`}>
        <PetitionTimeline entries={petition.timeline} />
      </Block>
    </div>
  );
}
