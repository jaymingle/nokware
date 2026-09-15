"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOptGroup, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useLinkedIssue } from "@/lib/api/petition-queries";
import { voicesLine } from "@/lib/voices";

import type { DraftState } from "@/hooks/use-petition-draft";
import type { AreaOption, PetitionOptions } from "@/lib/api/types";

const TITLE_MAX = 150;
const BODY_MAX = 4000;

type FieldsProps = { draft: DraftState; change: (next: Partial<DraftState>) => void; options: PetitionOptions; testId: string };

function Counted({ value, max }: { value: string; max: number }) {
  return <span className="text-[12px] text-ink-muted tabular-nums">{value.length.toLocaleString()} / {max.toLocaleString()}</span>;
}

function bySubMetro(areas: AreaOption[]): [string, AreaOption[]][] {
  const groups = new Map<string, AreaOption[]>();
  for (const area of areas) groups.set(area.sub_metro, [...(groups.get(area.sub_metro) ?? []), area]);
  return [...groups.entries()];
}

function Scope({ draft, change, options, testId }: FieldsProps) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[14px] font-medium">Where</legend>
      {(["area", "metro"] as const).map((scope) => (
        <label key={scope} className="flex items-center gap-2.5 text-[14px]">
          <input type="radio" name={`${testId}-scope`} checked={draft.scope === scope} onChange={() => change({ scope })}
            className="size-4 accent-teal" data-testid={`${testId}-scope-${scope}`} />
          {scope === "area" ? `One electoral area (needs ${options.threshold_area} signatures)` : `The whole Assembly (needs ${options.threshold_metro} signatures)`}
        </label>
      ))}
      {draft.scope === "area" ? (
        <NativeSelect value={draft.ward} onChange={(e) => change({ ward: e.target.value })} aria-label="Electoral area" className="ml-6.5" data-testid={`${testId}-ward`}>
          <NativeSelectOption value="">Choose the electoral area</NativeSelectOption>
          {bySubMetro(options.areas).map(([subMetro, areas]) => (
            <NativeSelectOptGroup key={subMetro} label={subMetro}>
              {areas.map((a) => <NativeSelectOption key={a.id} value={a.id}>{a.name}</NativeSelectOption>)}
            </NativeSelectOptGroup>
          ))}
        </NativeSelect>
      ) : null}
    </fieldset>
  );
}

function Words({ draft, change, testId }: Omit<FieldsProps, "options">) {
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${testId}-title`}>What are you asking the Assembly to do?</Label>
        <Input id={`${testId}-title`} value={draft.title} onChange={(e) => change({ title: e.target.value })} maxLength={TITLE_MAX}
          placeholder="e.g. Desilt the drain on Kaneshie market road before the rains" data-testid={`${testId}-title`} />
        <Counted value={draft.title} max={TITLE_MAX} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${testId}-body`}>Why</Label>
        <Textarea id={`${testId}-body`} value={draft.body} onChange={(e) => change({ body: e.target.value })} maxLength={BODY_MAX} rows={7}
          data-testid={`${testId}-body`} />
        <p className="text-[12.5px] text-ink-soft">
          What is happening, who it affects, and what has been tried. No one&apos;s phone number, address or ID: the petition is public.
        </p>
        <Counted value={draft.body} max={BODY_MAX} />
      </div>
    </>
  );
}

/** The open issue residents reported that this petition builds on, by what it is, not its ID. */
function IssueLink({ issue, onRemove, testId }: { issue: string; onRemove: () => void; testId: string }) {
  const linked = useLinkedIssue(issue);
  const place = [linked.data?.ward, linked.data?.sub_metro].filter(Boolean).join(", ");
  const text = linked.data ? `Builds on an open issue residents reported: ${linked.data.topic}${place ? ` · ${place}` : ""}. ${voicesLine(linked.data.voices)}.`
    : linked.error ? "The issue this was linked to isn't open any more, so it can't be linked. Remove it to send the petition." : "Builds on an open issue residents reported.";
  return (
    <p className="flex flex-wrap items-center gap-2 rounded-lg bg-paper-subtle px-3 py-2 text-[13px]" data-testid={`${testId}-issue`}>
      {text}
      <Button variant="ghost" size="xs" onClick={onRemove} data-testid={`${testId}-issue-remove`}>Remove</Button>
    </p>
  );
}

/** The petition's fields: the ask, why, its topic and where. Shared by a new petition and a refused one being edited. */
export function DraftFields({ draft, change, options, testId }: FieldsProps) {
  return (
    <div className="flex flex-col gap-5">
      <Words draft={draft} change={change} testId={testId} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${testId}-topic`}>Topic</Label>
        <NativeSelect id={`${testId}-topic`} value={draft.topic} onChange={(e) => change({ topic: e.target.value })} data-testid={`${testId}-topic`}>
          <NativeSelectOption value="">Choose a topic</NativeSelectOption>
          {options.topics.map((t) => <NativeSelectOption key={t.id} value={t.id}>{t.name}</NativeSelectOption>)}
        </NativeSelect>
      </div>
      <Scope draft={draft} change={change} options={options} testId={testId} />
      {draft.issue ? <IssueLink issue={draft.issue} onRemove={() => change({ issue: null })} testId={testId} /> : null}
    </div>
  );
}
