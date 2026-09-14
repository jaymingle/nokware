"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";

import { ContactList } from "@/components/contacts/contact-list";
import { Tag } from "@/components/documents/tag";
import { PreferencesForm } from "@/components/report/preferences-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { joinNames } from "@/lib/text";

import type { ReportReceipt } from "@/lib/api/types";

function CopyReference({ reference }: { reference: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard.writeText(reference).then(() => setCopied(true), () => setCopied(false));
  return (
    <Button type="button" variant="secondary" size="sm" onClick={copy} data-testid="report-copy-reference">
      {copied ? <CheckIcon data-icon="inline-start" /> : <CopyIcon data-icon="inline-start" />}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function messagesLine(receipt: ReportReceipt): string | null {
  if (receipt.held_for_consent) return null; // answered below
  if (!receipt.messages_on) return "No messages will be sent. You can check progress with the reference at any time.";
  if (receipt.private) return "You will get a message when it is received and when it is completed. Messages give only the reference.";
  return "A message confirming it is on its way to you. You will get another when it is resolved.";
}

/** Filed as personal safety by the classifier, though the citizen used the everyday form. */
function HeldForConsent({ receipt }: { receipt: ReportReceipt }) {
  return (
    <section className="flex flex-col gap-3 rounded-xl bg-brick-tint p-4 text-ink" data-testid="report-held">
      <h3 className="text-[18px]">Filed as a report about someone&apos;s safety</h3>
      <p className="text-[14px]">
        From what you wrote, Nokware has filed this as a report about someone&apos;s safety, so it is handled privately
        and never appears on the public dashboard.
      </p>
      {receipt.preferences_token ? <PreferencesForm reference={receipt.reference} token={receipt.preferences_token} /> : null}
    </section>
  );
}

function Filed({ receipt }: { receipt: ReportReceipt }) {
  const where = receipt.private
    ? `Sent to ${joinNames(receipt.recipients)}, and to no one else.`
    : `Filed under ${receipt.topic ?? "Other"} and sent to ${joinNames(receipt.recipients)}.`;
  const keep = receipt.private
    ? "Keep it somewhere private. Anyone who has it can see how far along the case is, though not what you reported."
    : "Keep it: it is the only way to follow your report. Nokware never asks your name.";
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12.5px] text-ink-soft">Your reference</p>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-heading text-[40px] leading-none tracking-wide tabular-nums" data-testid="report-reference">
          {receipt.reference}
        </h2>
        <CopyReference reference={receipt.reference} />
      </div>
      <p className="text-[14px] text-ink-soft">{keep}</p>
      <p className="text-[14.5px]" data-testid="report-routed">{where}</p>
    </div>
  );
}

/** The confirmation: the reference to keep, where the report went, and what messages to expect. */
export function ReportReceiptView({ receipt, onAnother }: { receipt: ReportReceipt; onAnother: () => void }) {
  const messages = messagesLine(receipt);
  return (
    <Card className="border-teal" data-testid="report-receipt">
      <CardContent className="flex flex-col gap-5 py-2 sm:px-6 sm:py-4">
        <div>
          <Tag tone="teal">Report filed</Tag>
        </div>
        <Filed receipt={receipt} />
        {messages ? <p className="text-[14px] text-ink-soft" data-testid="report-messages">{messages}</p> : null}
        {receipt.held_for_consent ? <HeldForConsent receipt={receipt} /> : null}
        <ContactList
          title={receipt.private ? "If you need help now" : "Numbers for this report"}
          contacts={receipt.contacts}
          testId="report-receipt-contacts"
        />
        <div className="flex flex-wrap gap-2 border-t pt-4">
          <Button asChild>
            <Link href="/report/status" data-testid="report-go-status">Check its status</Link>
          </Button>
          <Button variant="secondary" onClick={onAnother} data-testid="report-another">
            File another report
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
