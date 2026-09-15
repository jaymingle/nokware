"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import { useState } from "react";

import { RtiPanel } from "@/components/ask/rti-panel";
import { PageIntro } from "@/components/portal/page-intro";
import { Button } from "@/components/ui/button";
import { requestWording } from "@/lib/accountability";

const FIELD_MAX = 120;

/** A query value as plain, short text: it only ever fills in suggested wording. */
function clean(value: string | undefined): string | null {
  const text = value?.replace(/\p{Cc}/gu, " ").trim().slice(0, FIELD_MAX);
  return text ? text : null;
}

function Wording({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
  };
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:p-5" data-testid="rti-wording">
      <h2 className="text-[18px]">What to ask for</h2>
      <p className="text-[15px]" data-testid="rti-wording-text">{text}</p>
      <Button variant="secondary" size="sm" className="w-fit" onClick={copy} data-testid="rti-wording-copy">
        {copied ? <CheckIcon data-icon="inline-start" /> : <CopyIcon data-icon="inline-start" />}
        {copied ? "Copied" : "Copy the wording"}
      </Button>
    </div>
  );
}

/** How to request a document the Assembly hasn't published, with the wording ready when a gap sent the reader here. */
export function RtiPage({ document, period, elsewhere }: { document?: string; period?: string; elsewhere?: boolean }) {
  const name = clean(document);
  const when = clean(period);
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <PageIntro eyebrow="Right to Information" title="Request a document">
        How to ask the Assembly for a document it hasn&apos;t published. Nokware doesn&apos;t send requests for you: you send yours to the
        Assembly&apos;s Information Unit.
      </PageIntro>
      {name && when ? <Wording text={requestWording(name, when, Boolean(elsewhere))} /> : null}
      <RtiPanel testId="rti-page-panel" />
    </div>
  );
}
