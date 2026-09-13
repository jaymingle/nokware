"use client";

import type { ReactNode } from "react";

import { FormField } from "@/components/documents/document-fields";
import { Input } from "@/components/ui/input";
import { hasNumber, type Contact } from "@/lib/report/form";

// The consent wording is fixed: it is exactly what the citizen agrees to.
export const NOTIFY_CONSENT =
  "Send me a message when this is received and when it is completed. Messages give only the reference, never what it is about.";
export const CALLBACK_CONSENT = "Allow Police and Social Welfare to call you on this number about this case.";

type ContactProps = { contact: Contact; onChange: (contact: Contact) => void };

/** Phone and WhatsApp numbers. On the safety form, the browser is asked not to remember them. */
export function NumberFields({ contact, onChange, sensitive }: ContactProps & { sensitive: boolean }) {
  const autoComplete = sensitive ? "off" : "tel";
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField id="phone" label="Phone number for text messages">
        <Input id="phone" type="tel" inputMode="tel" autoComplete={autoComplete} placeholder="e.g. 024 123 4567" maxLength={20}
          value={contact.phone} onChange={(e) => onChange({ ...contact, phone: e.target.value })} data-testid="report-phone" />
      </FormField>
      <FormField id="whatsapp" label="WhatsApp number">
        <Input id="whatsapp" type="tel" inputMode="tel" autoComplete={autoComplete} placeholder="e.g. 024 123 4567" maxLength={20}
          value={contact.whatsapp} onChange={(e) => onChange({ ...contact, whatsapp: e.target.value })} data-testid="report-whatsapp" />
      </FormField>
    </div>
  );
}

export function ConsentBox({ checked, disabled = false, onChange, testId, children }: {
  checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void; testId: string; children: ReactNode;
}) {
  return (
    <label className="flex items-start gap-3 text-[14px] has-disabled:text-ink-soft">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 shrink-0 accent-teal" data-testid={testId} />
      <span>{children}</span>
    </label>
  );
}

/** Two separate, deliberate choices, both off until ticked. Giving a number agrees to neither. */
export function SafetyConsents({ contact, onChange }: ContactProps) {
  const numbered = hasNumber(contact);
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="sr-only">What the number may be used for</legend>
      <ConsentBox checked={contact.notify && numbered} disabled={!numbered} onChange={(notify) => onChange({ ...contact, notify })} testId="report-notify">
        {NOTIFY_CONSENT}
      </ConsentBox>
      <ConsentBox checked={contact.callbackConsent && numbered} disabled={!numbered}
        onChange={(callbackConsent) => onChange({ ...contact, callbackConsent })} testId="report-callback">
        {CALLBACK_CONSENT}
      </ConsentBox>
      <p className="text-[12.5px] text-ink-soft">
        {numbered ? "If you tick neither, your number is not sent at all." : "Add a number above to choose either of these."}
      </p>
    </fieldset>
  );
}
