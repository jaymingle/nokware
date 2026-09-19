"use client";

import { FlagIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePetitionOptions, useReportPetition } from "@/lib/api/petition-queries";
import { REPORT_HIDES_NOTHING } from "@/lib/petitions";

import type { PetitionGround, PetitionGroundOption } from "@/lib/api/types";

type Chosen = { ground: PetitionGround; duplicateOf: string; note: string };

const EMPTY: Chosen = { ground: "private_individual", duplicateOf: "", note: "" };

function Grounds({ grounds, chosen, onChoose }: { grounds: PetitionGroundOption[]; chosen: Chosen; onChoose: (ground: PetitionGround) => void }) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-1.5 text-[14px] font-medium">Why are you reporting it?</legend>
      {grounds.map((ground) => (
        <label key={ground.id} className="flex items-center gap-2.5 text-[14px]">
          <input type="radio" name="petition-report-ground" checked={chosen.ground === ground.id} onChange={() => onChoose(ground.id)}
            className="size-4 accent-teal" data-testid={`petition-report-ground-${ground.id}`} />
          {ground.label}
        </label>
      ))}
    </fieldset>
  );
}

/** A duplicate is the one ground that can't be judged alone: the contributor needs the other petition. */
function DuplicateNumber({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="petition-report-duplicate">The number of the petition this duplicates</Label>
      <Input id="petition-report-duplicate" value={value} onChange={(e) => onChange(e.target.value)} inputMode="numeric"
        autoComplete="off" placeholder="482 913" className="w-40 tabular-nums" data-testid="petition-report-duplicate" />
      <p className="text-[12.5px] text-ink-soft">It has to be a petition that is public now.</p>
    </div>
  );
}

function Note({ value, max, onChange }: { value: string; max: number; onChange: (value: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="petition-report-note">Anything to add (optional)</Label>
      <Textarea id="petition-report-note" value={value} onChange={(e) => onChange(e.target.value)} maxLength={max} rows={3}
        autoComplete="off" data-testid="petition-report-note" />
      <p className="text-[12px] text-ink-muted tabular-nums">{value.length.toLocaleString()} / {max.toLocaleString()}</p>
    </div>
  );
}

function needsNumber(grounds: PetitionGroundOption[], ground: PetitionGround): boolean {
  return grounds.some((g) => g.id === ground && g.needs_petition_number);
}

/** A duplicate's number is typed as it is read aloud, so the spaces come out before it is sent. */
function useReport(code: string, grounds: PetitionGroundOption[]) {
  const [chosen, setChosen] = useState<Chosen>(EMPTY);
  const report = useReportPetition(code);
  const wantsNumber = needsNumber(grounds, chosen.ground);
  const send = () => report.mutate({
    ground: chosen.ground,
    duplicate_of: wantsNumber ? chosen.duplicateOf.replace(/\D/g, "") : null,
    note: chosen.note.trim() || null,
  });
  const reset = () => { report.reset(); setChosen(EMPTY); };
  const change = (next: Partial<Chosen>) => setChosen((c) => ({ ...c, ...next }));
  return { chosen, change, report, wantsNumber, send, reset };
}

type Report = ReturnType<typeof useReport>;

function ReportFields({ state, grounds, noteMax }: { state: Report; grounds: PetitionGroundOption[]; noteMax: number }) {
  return (
    <div className="flex flex-col gap-4">
      <Grounds grounds={grounds} chosen={state.chosen} onChoose={(ground) => state.change({ ground })} />
      {state.wantsNumber ? <DuplicateNumber value={state.chosen.duplicateOf} onChange={(duplicateOf) => state.change({ duplicateOf })} /> : null}
      <Note value={state.chosen.note} max={noteMax} onChange={(note) => state.change({ note })} />
      {/* The API's own words, as it gave them: it is the only thing that knows why it refused. */}
      {state.report.error ? <ErrorNote testId="petition-report-error">{state.report.error.message}</ErrorNote> : null}
    </div>
  );
}

function Footer({ state, filed, ready, onClose }: { state: Report; filed: boolean; ready: boolean; onClose: () => void }) {
  return (
    <DialogFooter>
      <Button variant="secondary" onClick={onClose} data-testid="petition-report-close">{filed ? "Done" : "Cancel"}</Button>
      {filed ? null : (
        <Button disabled={state.report.isPending || !ready} onClick={state.send} data-testid="petition-report-send">
          {state.report.isPending ? "Sending…" : "Send the report"}
        </Button>
      )}
    </DialogFooter>
  );
}

export function ReportPetition({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const options = usePetitionOptions();
  const grounds = options.data?.grounds ?? [];
  const state = useReport(code, grounds);
  const { report } = state;
  const close = (next: boolean) => {
    setOpen(next);
    if (!next) state.reset();
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" data-testid="petition-report-open">
          <FlagIcon data-icon="inline-start" /> Report this petition
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg" data-testid="petition-report-dialog">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Report this petition</DialogTitle>
          <DialogDescription>{REPORT_HIDES_NOTHING} You don&apos;t need to sign in.</DialogDescription>
        </DialogHeader>
        {report.data ? (
          <p className="text-[14px]" data-testid="petition-report-filed">{report.data.message}</p>
        ) : (
          <ReportFields state={state} grounds={grounds} noteMax={options.data?.report_note_max ?? 300} />
        )}
        <Footer state={state} filed={report.data !== undefined} ready={grounds.length > 0} onClose={() => close(false)} />
      </DialogContent>
    </Dialog>
  );
}
