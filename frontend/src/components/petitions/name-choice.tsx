"use client";

import { Input } from "@/components/ui/input";
import { NAME_NOTE } from "@/lib/petitions";

const NAME_MAX = 80;

function Choice({ checked, onChange, testId, label, hint }: { checked: boolean; onChange: () => void; testId: string; label: string; hint: string }) {
  return (
    <label className="flex items-start gap-2.5 text-[14px]">
      <input type="radio" name="name-choice" checked={checked} onChange={onChange} className="mt-1 size-4 accent-teal" data-testid={testId} />
      <span className="flex flex-col">
        <span>{label}</span>
        <span className="text-[12.5px] text-ink-soft">{hint}</span>
      </span>
    </label>
  );
}

/** Anonymous by default. A name is shown publicly only if its owner chooses, and they're told first who can see it. */
export function NameChoice({ named, setNamed, name, setName, testId, anonymousHint }: {
  named: boolean; setNamed: (value: boolean) => void; name: string; setName: (value: string) => void; testId: string; anonymousHint: string;
}) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="sr-only">Anonymous or with your name</legend>
      <Choice checked={!named} onChange={() => setNamed(false)} testId={`${testId}-anonymous`} label="Stay anonymous" hint={anonymousHint} />
      <Choice checked={named} onChange={() => setNamed(true)} testId={`${testId}-named`} label="Show my name publicly"
        hint="Your name appears on the petition for anyone to see." />
      {named ? (
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={NAME_MAX} required placeholder="The name to show"
          aria-label="The name to show" autoComplete="name" className="ml-6.5 max-w-72" data-testid={`${testId}-name`} />
      ) : null}
      <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[13px]" data-testid={`${testId}-note`}>{NAME_NOTE}</p>
    </fieldset>
  );
}
