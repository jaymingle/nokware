"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { plural } from "@/lib/text";

import type { PetitionRemovals } from "@/lib/api/types";

const CODE_DIGITS = 6;

function Ground({ ground, label, count }: { ground: string; label: string; count: number }) {
  return (
    <li className="flex justify-between gap-3 border-b border-dashed py-1.5" data-testid={`removals-ground-${ground}`}>
      <span>{label}</span>
      <span className="tabular-nums">{count.toLocaleString()}</span>
    </li>
  );
}

/**
 * A number opens a removed petition's tombstone, so the page offers the one way in that exists. Six digits,
 * because that is what a petition's number is; anything else is not a petition number and is left alone.
 */
function ByNumber() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const digits = code.replace(/\D/g, "");
  const open = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (digits.length === CODE_DIGITS) router.push(`/petitions/${digits}`);
  };
  return (
    <form onSubmit={open} className="flex flex-wrap items-end gap-2" data-testid="removals-by-number">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="removals-code">Open a petition by its number</Label>
        <Input id="removals-code" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric"
          autoComplete="off" placeholder="482 913" className="w-40 tabular-nums" data-testid="removals-code" />
      </div>
      <Button type="submit" variant="secondary" disabled={digits.length !== CODE_DIGITS} data-testid="removals-open">Open it</Button>
    </form>
  );
}

/** The grounds the removed petitions below came down on, and the way in for a number a reader already has. */
export function RemovalRecord({ removals }: { removals: PetitionRemovals }) {
  return (
    <div className="flex flex-col gap-4" data-testid="petitions-removals">
      <p className="text-[14px]">
        {removals.total === 0
          ? "No petition has been removed."
          : `${plural(removals.total, "petition has", "petitions have")} been removed. A petition is taken down by a contributor on one of four grounds, never by the MCE, and the person who started it can mend the words and publish it again.`}
      </p>
      <ul className="grid gap-x-8 text-[13.5px] sm:grid-cols-2">
        {removals.grounds.map((g) => <Ground key={g.ground} ground={g.ground} label={g.label} count={g.count} />)}
      </ul>
      <p className="text-[13px] text-ink-soft">
        Nothing of a removed petition survives it but this record: not its words, not its photographs, not the
        names of the people who signed it.
      </p>
      <ByNumber />
    </div>
  );
}
