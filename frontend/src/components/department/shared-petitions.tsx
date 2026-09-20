"use client";

import Link from "next/link";

import { PetitionNoteForm } from "@/components/department/petition-note";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { Progress } from "@/components/petitions/petition-card";
import { StatusTag } from "@/components/status-tag";
import { useSharedPetitions } from "@/lib/api/queries";
import { useMe } from "@/lib/auth/auth-context";
import { placeLine, spacedCode } from "@/lib/petitions";
import { noteLine, splitShared } from "@/lib/portal/petitions";
import { petitionStatus } from "@/lib/status";

import type { SharedPetition } from "@/lib/api/types";

/**
 * What the MCE has asked this department to answer. Nothing here decides a petition: the department says what it
 * knows, once, and the answer stands on the public page under the department's name.
 */

function WrittenNote({ note, department }: { note: string; department: string }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-teal bg-teal-tint px-3 py-2.5">
      <p className="text-[12.5px] text-ink-soft">Published under {department}</p>
      <p className="text-[14px] whitespace-pre-line">{note}</p>
    </div>
  );
}

function SharedCard({ shared, department }: { shared: SharedPetition; department: string }) {
  const petition = shared.petition;
  const tag = petitionStatus(petition.status);
  return (
    <article className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid={`shared-petition-${petition.code}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={`/petitions/${petition.code}`} className="text-[16px] font-medium underline underline-offset-2"
          data-testid={`shared-petition-${petition.code}-link`}>
          {petition.title}
        </Link>
        <StatusTag tone={tag.tone} testId={`shared-petition-${petition.code}-status`}>{tag.label}</StatusTag>
      </div>
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)} · {noteLine(shared)}
      </p>
      <div className="max-w-sm"><Progress signatures={petition.signatures} threshold={petition.threshold} /></div>
      {shared.note
        ? <WrittenNote note={shared.note} department={department} />
        : <PetitionNoteForm code={petition.code} />}
    </article>
  );
}

function CardList({ label, shared, department }: { label: string; shared: SharedPetition[]; department: string }) {
  return (
    <section aria-label={label} className="flex flex-col gap-4">
      <h2 className="text-[19px]">{label}</h2>
      {shared.map((item) => <SharedCard key={item.petition.code} shared={item} department={department} />)}
    </section>
  );
}

export function SharedPetitions() {
  const me = useMe();
  const department = me.department_name ?? "your department";
  const { data, error, isPending, refetch } = useSharedPetitions();
  if (isPending) return <LoadingPanel label="Loading the petitions shared with you…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  const { waiting, answered } = splitShared(data);
  if (data.length === 0) {
    return (
      <EmptyPanel title="No petition has been shared with you">
        When the MCE asks {department} to answer a petition, it appears here with the petition as residents read it.
      </EmptyPanel>
    );
  }
  return (
    <div className="flex flex-col gap-8">
      {waiting.length > 0 ? <CardList label="Waiting for your note" shared={waiting} department={department} /> : null}
      {answered.length > 0 ? <CardList label="Answered" shared={answered} department={department} /> : null}
    </div>
  );
}
