"use client";

import { useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { normaliseReference } from "@/lib/report/reference";

const NOT_A_REFERENCE = "That doesn't look like a reference. It has eight letters and numbers, like K7QM-4TXP.";

type StatusLookupProps = { busy: boolean; showing: boolean; onLookup: (reference: string) => void; onClear: () => void };

/** The reference box. Nothing is looked up until it reads as a reference; nothing goes in the address bar. */
export function StatusLookup({ busy, showing, onLookup, onClear }: StatusLookupProps) {
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const reference = normaliseReference(typed);
    setProblem(reference ? null : NOT_A_REFERENCE);
    if (reference) onLookup(reference);
    else onClear(); // no earlier result or error left under the new message
  };
  const clear = () => {
    setTyped("");
    setProblem(null);
    onClear();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2" data-testid="status-lookup">
      <Label htmlFor="reference">Your reference</Label>
      <div className="flex flex-wrap gap-2">
        <Input id="reference" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="e.g. K7QM-4TXP" autoComplete="off"
          autoCapitalize="characters" spellCheck={false} required className="max-w-60 font-medium tracking-wide uppercase" data-testid="status-reference" />
        <Button type="submit" disabled={busy} data-testid="status-lookup-submit">
          {busy ? "Looking…" : "Look up"}
        </Button>
        {showing ? (
          <Button type="button" variant="ghost" onClick={clear} data-testid="status-clear">
            Clear
          </Button>
        ) : null}
      </div>
      {problem ? <ErrorNote testId="status-reference-problem">{problem}</ErrorNote> : null}
    </form>
  );
}
