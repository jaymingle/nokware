"use client";

import { MessageCircleIcon, PhoneIcon, SmartphoneIcon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePhoneChallenge } from "@/hooks/use-phone-challenge";
import { confirmSmsCode, sendSmsCode } from "@/lib/api/petitions";
import { spacedCode, type KeptChallenge, type KeptProof } from "@/lib/petitions";

import type { PhoneChallengeStatus } from "@/lib/api/types";

const PHONE_PRIVACY =
  "Ghanaian mobile numbers (+233) only. Nokware never shows your number. It keeps a scrambled form of it, so you can find your petition again, and the number itself only to send you updates about your petition, deleted 30 days after the petition closes.";

function Way({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3 rounded-lg border bg-paper-subtle px-4 py-3">
      <span aria-hidden className="mt-0.5 text-teal">{icon}</span>
      <div className="flex min-w-0 flex-col gap-1.5 text-[13.5px]">
        <p className="font-medium">{title}</p>
        {children}
      </div>
    </li>
  );
}

function useSmsCode(challenge: KeptChallenge, settle: (status: PhoneChallengeStatus) => void) {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  };
  const send = (phone: string) => run(async () => setSentTo((await sendSmsCode(challenge.challenge, phone)).sent_to));
  const confirm = (code: string) => run(async () => settle(await confirmSmsCode(challenge.challenge, code)));
  return { sentTo, error, busy, send, confirm };
}

function SmsWay({ challenge, settle }: { challenge: KeptChallenge; settle: (status: PhoneChallengeStatus) => void }) {
  const sms = useSmsCode(challenge, settle);
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("value") ?? "").trim();
    void (sms.sentTo ? sms.confirm(value) : sms.send(value));
  };
  return (
    <Way icon={<SmartphoneIcon className="size-4" />} title="By SMS">
      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2">
        <Input key={sms.sentTo ? "code" : "phone"} name="value" required inputMode={sms.sentTo ? "numeric" : "tel"}
          autoComplete={sms.sentTo ? "one-time-code" : "tel"} placeholder={sms.sentTo ? "The 6-digit code" : "024 123 4567"}
          aria-label={sms.sentTo ? "The code from the SMS" : "Your mobile number"} className="max-w-48" data-testid="phone-sms-input" />
        <Button type="submit" variant="secondary" size="sm" disabled={sms.busy} data-testid="phone-sms-submit">
          {sms.sentTo ? "Confirm" : "Text me a code"}
        </Button>
      </form>
      {sms.sentTo ? <p className="text-ink-soft">Sent to {sms.sentTo}. It lasts 15 minutes.</p> : null}
      {sms.error ? <ErrorNote testId="phone-sms-error">{sms.error}</ErrorNote> : null}
    </Way>
  );
}

function Ways({ challenge, settle }: { challenge: KeptChallenge; settle: (status: PhoneChallengeStatus) => void }) {
  const none = !challenge.whatsapp_url && !challenge.ussd_code && !challenge.sms;
  return (
    <ul className="flex flex-col gap-2">
      {challenge.whatsapp_url ? (
        <Way icon={<MessageCircleIcon className="size-4" />} title="On WhatsApp">
          <p className="text-ink-soft">This opens a chat with Nokware with the code already typed. Send it, then come back to this page.</p>
          <Button asChild size="sm" className="w-fit">
            <a href={challenge.whatsapp_url} target="_blank" rel="noopener noreferrer" data-testid="phone-whatsapp">Send the code on WhatsApp</a>
          </Button>
        </Way>
      ) : null}
      {challenge.ussd_code ? (
        <Way icon={<PhoneIcon className="size-4" />} title="By dialling, on any phone">
          <p className="text-ink-soft" data-testid="phone-ussd">
            Dial <strong className="font-medium text-ink">{challenge.ussd_code}</strong>, choose 5, &ldquo;Confirm a web code&rdquo;, and type the code.
          </p>
        </Way>
      ) : null}
      {challenge.sms ? <SmsWay challenge={challenge} settle={settle} /> : null}
      {none ? <li className="text-[13.5px] text-ink-soft">Confirming a number isn&apos;t set up on this server yet.</li> : null}
    </ul>
  );
}

function Waiting({ challenge, settle, onCancel }: { challenge: KeptChallenge; settle: (s: PhoneChallengeStatus) => void; onCancel: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13.5px]">
        Your code is{" "}
        <strong className="font-heading text-[26px] leading-none tracking-wide tabular-nums" data-testid="phone-code">{spacedCode(challenge.code)}</strong>
      </p>
      <Ways challenge={challenge} settle={settle} />
      <p className="text-[12.5px] text-ink-soft" aria-live="polite" data-testid="phone-waiting">
        Waiting for your code… This page carries on by itself once it arrives. Codes last 15 minutes.
      </p>
      <Button variant="ghost" size="sm" className="w-fit" onClick={onCancel} data-testid="phone-cancel">Start again</Button>
    </div>
  );
}

export function PhoneConfirm({ onConfirmed, lead }: { onConfirmed: (proof: KeptProof) => void; lead: string }) {
  const phone = usePhoneChallenge(onConfirmed);
  return (
    <div className="flex flex-col gap-3" data-testid="phone-confirm">
      <p className="text-[14px]">{lead}</p>
      {phone.challenge ? (
        <Waiting challenge={phone.challenge} settle={phone.settle} onCancel={phone.cancel} />
      ) : (
        <Button className="w-fit" onClick={() => void phone.start()} disabled={phone.starting} data-testid="phone-start">
          {phone.starting ? "Getting a code…" : "Get a code"}
        </Button>
      )}
      {phone.error ? <ErrorNote testId="phone-error">{phone.error}</ErrorNote> : null}
      <p className="text-[12.5px] text-ink-soft">{PHONE_PRIVACY}</p>
    </div>
  );
}

export function PhoneConfirmed({ proof, onForget }: { proof: KeptProof; onForget: () => void }) {
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px]" data-testid="phone-confirmed">
      <span>Confirmed: <strong className="font-medium tabular-nums">{proof.number}</strong></span>
      <Button variant="ghost" size="sm" onClick={onForget} data-testid="phone-forget">Use another number</Button>
    </p>
  );
}
