"use client";

import { useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { PhotoField } from "@/components/report/photo-field";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useEscalateReport, useReportOptions } from "@/lib/api/public-queries";
import { NOTE_MAX } from "@/lib/limits";
import { formatDate } from "@/lib/time";

import type { Sending } from "@/lib/api/upload";
import type { ReportPhoto } from "@/lib/report/photos";

type EscalateFormProps = { reference: string; until: string; intro: string; action: string };

function sendingLabel(sending: Sending | null): string {
  if (sending === null || sending === "filing") return "Sending…";
  return `Sending your photos… ${Math.round((sending.sent / Math.max(sending.total, 1)) * 100)}%`;
}

/** One escalation, within 14 days of the resolution. Photos are shrunk and stripped of EXIF in the browser first,
    exactly as they are when a report is filed. */
export function EscalateForm({ reference, until, intro, action }: EscalateFormProps) {
  const [sending, setSending] = useState<Sending | null>(null);
  const escalate = useEscalateReport(setSending);
  const options = useReportOptions();
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState<ReportPhoto[]>([]);
  const limits = {
    maxPhotos: options.data?.max_escalation_photos ?? 5,
    maxBytes: options.data?.max_photo_bytes ?? 10 * 1024 * 1024,
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSending({ sent: 0, total: 1 });
    escalate.mutate({ reference, note: note.trim(), photos: photos.map((photo) => photo.file) },
                    { onError: () => setSending(null) });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t pt-5" data-testid="status-escalate">
      <p className="text-[14px]">
        {intro} You can do this once, until {formatDate(until)}.
      </p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="escalation-note">What is still wrong?</Label>
        <Textarea id="escalation-note" value={note} onChange={(e) => setNote(e.target.value)} required maxLength={NOTE_MAX}
          autoComplete="off" rows={3} data-testid="status-escalate-note" />
      </div>
      <PhotoField photos={photos} onChange={setPhotos} limits={limits}
        hint="Location and camera details are removed before they are stored." />
      {escalate.error ? <ErrorNote testId="status-escalate-error">{escalate.error.message}</ErrorNote> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="secondary" disabled={escalate.isPending || !note.trim()} data-testid="status-escalate-submit">
          {escalate.isPending ? sendingLabel(sending) : action}
        </Button>
        {escalate.isPending ? (
          <span className="text-[12.5px] text-ink-soft" aria-live="polite" data-testid="status-escalate-progress">
            {sendingLabel(sending)}
          </span>
        ) : null}
      </div>
    </form>
  );
}
