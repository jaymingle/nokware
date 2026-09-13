"use client";

import { useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { CALLBACK_CONSENT, ConsentBox, NOTIFY_CONSENT } from "@/components/report/contact-fields";
import { Button } from "@/components/ui/button";
import { useReportPreferences } from "@/lib/api/public-queries";

import type { PreferencesResult } from "@/lib/api/types";

function Saved({ result, callback }: { result: PreferencesResult; callback: boolean }) {
  const messages = result.messages_on ? "Messages are on. They give only the reference, never what it is about." : "No messages will be sent.";
  return (
    <p role="status" className="text-[14px]" data-testid="report-preferences-saved">
      Saved. {messages} {callback ? "Police and Social Welfare may call you about this case." : "No one will call you."}
    </p>
  );
}

/** The one-time choice, within the hour, for a report the classifier filed as personal safety. */
export function PreferencesForm({ reference, token }: { reference: string; token: string }) {
  const save = useReportPreferences();
  const [notify, setNotify] = useState(false);
  const [callback, setCallback] = useState(false);
  if (save.data) return <Saved result={save.data} callback={callback} />;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate({ reference, token, choice: { notify, callback_consent: callback } });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3" data-testid="report-preferences">
      <p className="text-[14px]">You gave a number before knowing this, so no messages have been sent. Choose what you would like:</p>
      <ConsentBox checked={notify} onChange={setNotify} testId="report-preferences-notify">
        {NOTIFY_CONSENT}
      </ConsentBox>
      <ConsentBox checked={callback} onChange={setCallback} testId="report-preferences-callback">
        {CALLBACK_CONSENT}
      </ConsentBox>
      {save.error ? <ErrorNote testId="report-preferences-error">{save.error.message}</ErrorNote> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={save.isPending} data-testid="report-preferences-save">
          {save.isPending ? "Saving…" : "Save my choice"}
        </Button>
        <span className="text-[12.5px] text-ink-soft">You can choose once, within an hour of reporting.</span>
      </div>
    </form>
  );
}
