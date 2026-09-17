"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ErrorNote, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { DraftFields } from "@/components/petitions/draft-fields";
import { LedgerMatches } from "@/components/petitions/ledger-matches";
import { NameChoice } from "@/components/petitions/name-choice";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { PageIntro } from "@/components/portal/page-intro";
import { Button } from "@/components/ui/button";
import { useMounted } from "@/hooks/use-mounted";
import { checkKey, toRequest, usePetitionDraft, type DraftState } from "@/hooks/use-petition-draft";
import { usePhoneProof } from "@/hooks/use-phone-proof";
import { ApiError } from "@/lib/api/errors";
import { useCheckDraft, useDraftLedger, usePetitionOptions, useSubmitPetition } from "@/lib/api/petition-queries";
import { spacedCode } from "@/lib/petitions";
import { formatDateTime } from "@/lib/time";

import type { LedgerMatch, OwnPetition, PetitionOptions, ScreenResult } from "@/lib/api/types";

const CITE_MAX = 3;

type Checked = { key: string; screen: ScreenResult };
type Found = { key: string; matches: LedgerMatch[] };

function Step({ number, title, children, testId }: { number: number; title: string; children: ReactNode; testId: string }) {
  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-card p-5 sm:p-6" data-testid={testId}>
      <h2 className="text-[19px]"><span className="mr-2 text-ink-muted tabular-nums">{number}.</span>{title}</h2>
      {children}
    </section>
  );
}

/**
 * The draft's words checked, then what the Ledger holds on its subject. Only the check decides whether the
 * petition can be sent: the Ledger search is context, so if it fails the creator can still send it.
 */
function useDraftCheck(draft: DraftState) {
  const screen = useCheckDraft();
  const ledger = useDraftLedger();
  const [checked, setChecked] = useState<Checked | null>(null);
  const [found, setFound] = useState<Found | null>(null);
  const run = async () => {
    const key = checkKey(draft);
    const words = { title: draft.title, body: draft.body };
    ledger.reset();
    try {
      const result = await screen.mutateAsync(words);
      setChecked({ key, screen: result });
      if (!result.stop) setFound({ key, matches: await ledger.mutateAsync({ ...words, topic: draft.topic }) });
    } catch {
      // screen.error or ledger.error says what failed
    }
  };
  const key = checkKey(draft);
  return {
    run, current: checked?.key === key ? checked : null, matches: found?.key === key ? found.matches : null,
    checking: screen.isPending, searching: ledger.isPending, error: screen.error, ledgerError: ledger.error,
  };
}

function LedgerSuggestions({ check, draft, change }: { check: ReturnType<typeof useDraftCheck>; draft: DraftState; change: (next: Partial<DraftState>) => void }) {
  const chosen = new Set(draft.documents);
  const toggle = (id: string) => change({ documents: chosen.has(id) ? draft.documents.filter((d) => d !== id) : [...draft.documents, id] });
  return (
    <div className="flex flex-col gap-2" data-testid="petition-draft-ledger-section">
      <h3 className="text-[15px] font-medium">What The Ledger already holds on this</h3>
      <p className="text-[13px] text-ink-soft">
        The Assembly may already have a plan or a budget line for this: cite it to strengthen your case, or to show a
        commitment that wasn&apos;t kept. Cite up to {CITE_MAX}.
      </p>
      {check.searching ? <p className="text-[13.5px] text-ink-soft">Searching the Assembly&apos;s documents…</p> : null}
      {check.ledgerError ? (
        <p className="text-[13.5px] text-ink-soft" data-testid="petition-draft-ledger-error">
          The Ledger couldn&apos;t be searched just now. You can still send your petition, or check again later to cite documents.
        </p>
      ) : null}
      {check.matches ? (
        <LedgerMatches matches={check.matches} testId="petition-draft-ledger" cite={{ chosen, toggle, full: draft.documents.length >= CITE_MAX }} />
      ) : null}
    </div>
  );
}

function CheckResult({ check, draft, change }: { check: ReturnType<typeof useDraftCheck>; draft: DraftState; change: (next: Partial<DraftState>) => void }) {
  const screen = check.current?.screen;
  if (!screen) return null;
  return (
    <div className="flex flex-col gap-4">
      {screen.stop ? <ErrorNote testId="petition-check-stop">{screen.stop}</ErrorNote> : null}
      {screen.warning ? <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[13.5px]" data-testid="petition-check-warning">{screen.warning}</p> : null}
      {!screen.stop && !screen.warning ? <p className="text-[13.5px] text-teal" data-testid="petition-check-passed">Checked: nothing in it stops it being published.</p> : null}
      {!screen.stop ? <LedgerSuggestions check={check} draft={draft} change={change} /> : null}
    </div>
  );
}

function WhatHappensNext({ options }: { options: PetitionOptions }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-paper-subtle px-4 py-3 text-[13.5px]" data-testid="petition-next">
      <p className="font-medium">What happens next</p>
      <p>The MCE has {options.review_hours} hours to publish your petition or refuse it, and can refuse it only for one of these reasons:</p>
      <ul className="list-disc pl-5 text-ink-soft">
        {options.refusal_reasons.map((r) => <li key={r.id}>{r.label}</li>)}
      </ul>
      <p>
        If the MCE doesn&apos;t decide within {options.review_hours} hours, it publishes automatically. Once published, it is
        open for {options.open_days} days.
      </p>
    </div>
  );
}

function Submitted({ petition }: { petition: OwnPetition }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 rounded-xl border bg-card p-6" data-testid="petition-submitted">
      <h1 className="text-[28px]">Sent to the MCE</h1>
      <p className="text-[15px]">
        Your petition is number <strong className="font-medium tabular-nums">{spacedCode(petition.code)}</strong>. The MCE can
        publish it or refuse it for one of the stated reasons.
        {petition.review_deadline ? ` If they haven't decided by ${formatDateTime(petition.review_deadline)}, it publishes automatically.` : ""}
      </p>
      <Button asChild className="w-fit"><Link href="/petitions/mine" data-testid="petition-submitted-mine">Follow it in your petitions</Link></Button>
    </div>
  );
}

function useSubmit(draft: DraftState, named: boolean, name: string, onDone: (petition: OwnPetition) => void, onExpired: () => void) {
  const submit = useSubmitPetition();
  const send = async (proof: string) => {
    try {
      onDone(await submit.mutateAsync({ submission: { ...toRequest(draft), show_name: named, name: named ? name : null }, proof }));
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
    }
  };
  return { send, pending: submit.isPending, error: submit.error };
}

function Send({ ready, submit, proof }: { ready: boolean; submit: ReturnType<typeof useSubmit>; proof: string | null }) {
  return (
    <div className="flex flex-col gap-2">
      {submit.error ? <ErrorNote testId="petition-submit-error">{submit.error.message}</ErrorNote> : null}
      <Button className="w-fit" disabled={!ready || submit.pending} onClick={() => proof && void submit.send(proof)} data-testid="petition-submit">
        {submit.pending ? "Sending…" : "Send to the MCE for review"}
      </Button>
      {!ready ? <p className="text-[12.5px] text-ink-soft">Check your petition and confirm your phone to send it.</p> : null}
    </div>
  );
}

function Form({ options, issue }: { options: PetitionOptions; issue: string | null }) {
  const [draft, change, clear] = usePetitionDraft(issue);
  const [named, setNamed] = useState(false);
  const [name, setName] = useState("");
  const [done, setDone] = useState<OwnPetition | null>(null);
  const phone = usePhoneProof();
  const check = useDraftCheck(draft);
  const submit = useSubmit(draft, named, name, (petition) => { clear(); setDone(petition); }, phone.forget);
  if (done) return <Submitted petition={done} />;
  const ready = check.current !== null && !check.current.screen.stop && phone.proof !== null;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <Step number={1} title="Your petition" testId="petition-step-words">
        <DraftFields draft={draft} change={change} options={options} testId="petition-draft" />
        <Button variant="secondary" className="w-fit" onClick={() => void check.run()} disabled={check.checking || check.searching} data-testid="petition-check">
          {check.checking ? "Checking…" : check.current ? "Check again" : "Check my petition"}
        </Button>
        {check.error ? <ErrorNote testId="petition-check-error">{check.error.message}</ErrorNote> : null}
        <CheckResult check={check} draft={draft} change={change} />
      </Step>
      <Step number={2} title="Your name" testId="petition-step-name">
        <NameChoice named={named} setNamed={setNamed} name={name} setName={setName} testId="petition-name"
          anonymousHint="The petition says “Started by a resident”." />
      </Step>
      <Step number={3} title="Confirm your phone" testId="petition-step-phone">
        {phone.proof ? <PhoneConfirmed proof={phone.proof} onForget={phone.forget} />
          : <PhoneConfirm onConfirmed={phone.confirm} lead="Confirm the number that's starting this petition." />}
      </Step>
      <WhatHappensNext options={options} />
      <Send ready={ready} submit={submit} proof={phone.proof?.token ?? null} />
    </div>
  );
}

/** Starting a petition: write it, see what the Ledger holds, choose whether to show a name, confirm a phone, send it. */
export function NewPetitionPage({ issue }: { issue: string | null }) {
  const mounted = useMounted();
  const options = usePetitionOptions();
  return (
    <>
      <PageIntro eyebrow="Petitions" title="Start a petition">
        Ask the Accra Metropolitan Assembly to do something, and gather support for it. Your draft is kept in this browser
        until you send it.
      </PageIntro>
      {options.isPending || !mounted ? <LoadingPanel label="Loading…" /> : null}
      {options.error ? <ErrorPanel message={options.error.message} onRetry={() => void options.refetch()} /> : null}
      {options.data && mounted ? <Form options={options.data} issue={issue} /> : null}
    </>
  );
}
