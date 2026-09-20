"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { LedgerMatches } from "@/components/petitions/ledger-matches";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { usePetitionLedger } from "@/lib/api/petition-queries";
import { useDepartments, useRespondToPetition } from "@/lib/api/queries";
import { spacedCode } from "@/lib/petitions";

import type { ResponseKind } from "@/lib/api/types";

const TEXT_MAX = 4000;
const CITE_MAX = 3;
const KINDS: { id: ResponseKind; label: string; hint: string }[] = [
  { id: "will_act", label: "The Assembly will act", hint: "Say what it will do, and by when if you can." },
  { id: "referred", label: "Referred to a department", hint: "Name the department, and what it has been asked to do." },
  { id: "cannot_act", label: "The Assembly can't act", hint: "Say why." },
];

type Draft = { kind: ResponseKind | ""; department: string; text: string; documents: string[] };

function KindChoice({ draft, change, code }: { draft: Draft; change: (next: Partial<Draft>) => void; code: string }) {
  const departments = useDepartments();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[14px] font-medium">Your response</legend>
      {KINDS.map((k) => (
        <label key={k.id} className="flex items-start gap-2.5 text-[13.5px]">
          <input type="radio" name="kind" checked={draft.kind === k.id} onChange={() => change({ kind: k.id })} required
            className="mt-1 size-4 accent-teal" data-testid={`respond-${code}-kind-${k.id}`} />
          <span className="flex flex-col"><span>{k.label}</span><span className="text-[12.5px] text-ink-soft">{k.hint}</span></span>
        </label>
      ))}
      {draft.kind === "referred" ? (
        <NativeSelect value={draft.department} onChange={(e) => change({ department: e.target.value })} aria-label="The department"
          required className="ml-6.5" data-testid={`respond-${code}-department`}>
          <NativeSelectOption value="">Choose the department</NativeSelectOption>
          {departments.data?.map((d) => <NativeSelectOption key={d.id} value={d.id}>{d.name}</NativeSelectOption>)}
        </NativeSelect>
      ) : null}
    </fieldset>
  );
}

function Citable({ draft, change, code }: { draft: Draft; change: (next: Partial<Draft>) => void; code: string }) {
  const ledger = usePetitionLedger(code);
  const chosen = new Set(draft.documents);
  const toggle = (id: string) => change({ documents: chosen.has(id) ? draft.documents.filter((d) => d !== id) : [...draft.documents, id] });
  if (!ledger.data || ledger.data.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[14px] font-medium">Cite what The Ledger holds on this (optional, up to {CITE_MAX})</p>
      <LedgerMatches matches={ledger.data} testId={`respond-${code}-ledger`} cite={{ chosen, toggle, full: draft.documents.length >= CITE_MAX }} />
    </div>
  );
}

function Check({ draft, late, code }: { draft: Draft; late: boolean; code: string }) {
  const kind = KINDS.find((k) => k.id === draft.kind);
  return (
    <div className="flex flex-col gap-3" data-testid={`respond-${code}-check`}>
      <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[13.5px]">
        Your response: <strong className="font-medium">{kind?.label}</strong>
      </p>
      <p className="max-h-52 overflow-y-auto rounded-lg border px-3 py-2.5 text-[13.5px] whitespace-pre-line">{draft.text}</p>
      <p className="text-[14px]">
        This goes on the petition&apos;s page now, word for word, and can&apos;t be changed afterwards. The petition
        then takes no more signatures.{late ? " The page will say how many days late it came." : ""}
      </p>
    </div>
  );
}

function useResponse(code: string, draft: Draft, onDone: () => void) {
  const respond = useRespondToPetition();
  const send = async () => {
    if (!draft.kind) return;
    const response = { kind: draft.kind, text: draft.text, department: draft.kind === "referred" ? draft.department : null, documents: draft.documents };
    try {
      await respond.mutateAsync({ code, response });
      toast.success("Published on the petition's page. The person who started it is told.");
      onDone();
    } catch {
      // respond.error is shown in the dialog
    }
  };
  return { respond, send };
}

function RespondForm({ code, late, onDone }: { code: string; late: boolean; onDone: () => void }) {
  const [draft, setDraft] = useState<Draft>({ kind: "", department: "", text: "", documents: [] });
  const [checking, setChecking] = useState(false);
  const change = (next: Partial<Draft>) => setDraft((d) => ({ ...d, ...next }));
  const { respond, send } = useResponse(code, draft, onDone);
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (checking) void send();
    else setChecking(true);
  };
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {checking ? <Check draft={draft} late={late} code={code} /> : (
        <>
          <KindChoice draft={draft} change={change} code={code} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`respond-${code}-text`}>The statement</Label>
            <Textarea id={`respond-${code}-text`} value={draft.text} onChange={(e) => change({ text: e.target.value })} required
              minLength={50} maxLength={TEXT_MAX} rows={6} data-testid={`respond-${code}-text`} />
          </div>
          <Citable draft={draft} change={change} code={code} />
          {late ? <p className="rounded-lg bg-gold-tint px-3 py-2 text-[13px]">The 30 days have passed: the page will say how many days late this response came.</p> : null}
        </>
      )}
      {respond.error ? <ErrorNote>{respond.error.message}</ErrorNote> : null}
      <DialogFooter>
        {checking ? (
          <Button type="button" variant="secondary" onClick={() => setChecking(false)} data-testid={`respond-${code}-back`}>Back</Button>
        ) : (
          <DialogClose asChild><Button type="button" variant="secondary" data-testid={`respond-${code}-cancel`}>Cancel</Button></DialogClose>
        )}
        <Button type="submit" disabled={respond.isPending || !draft.kind} data-testid={`respond-${code}-confirm`}>
          {checking ? "Publish the response" : "Check it over"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function RespondDialog({ code, late }: { code: string; late: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="w-fit" data-testid={`respond-${code}`}>Respond publicly</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Respond to petition {spacedCode(code)}</DialogTitle>
          <DialogDescription>
            It is published on the petition&apos;s page as you write it, and can&apos;t be changed afterwards. The page says it came from
            the MCE; the audit trail keeps your name. The petition then takes no more signatures.
          </DialogDescription>
        </DialogHeader>
        {open ? <RespondForm code={code} late={late} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
