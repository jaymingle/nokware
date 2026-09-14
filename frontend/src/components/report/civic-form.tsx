"use client";

import { NumberFields } from "@/components/report/contact-fields";
import { DescriptionField } from "@/components/report/description-field";
import { FormActions, FormSection } from "@/components/report/form-parts";
import { Note } from "@/components/report/notes";
import { PhotoField } from "@/components/report/photo-field";
import { WardField } from "@/components/report/place-fields";
import { Card, CardContent } from "@/components/ui/card";
import { useReportForm } from "@/hooks/use-report-form";

import type { ReportOptions, ReportReceipt } from "@/lib/api/types";

export type ReportFormProps = { options: ReportOptions; onFiled: (receipt: ReportReceipt) => void; onBack: () => void };

/** An everyday problem: where it is, what it is, and a number for messages if the citizen wants them. */
export function CivicForm({ options, onFiled, onBack }: ReportFormProps) {
  const { photos, setPhotos, contact, setContact, submit, filing } = useReportForm(onFiled);
  const limits = { maxPhotos: options.max_photos, maxBytes: options.max_photo_bytes };
  return (
    <Card>
      <CardContent className="py-2 sm:px-6 sm:py-4">
        <form onSubmit={(event) => submit(event)} className="flex flex-col gap-6" data-testid="report-civic-form">
          <DescriptionField
            min={options.description_min}
            max={options.description_max}
            placeholder="e.g. the skip at the junction market has not been lifted in ten days"
            hint="Say what is wrong and exactly where: a street name or a landmark helps the department find it."
            sensitive={false}
          />
          <WardField subMetros={options.sub_metros} />
          <PhotoField photos={photos} onChange={setPhotos} limits={limits} hint="Location and camera details are removed before they are stored." />
          <FormSection
            title="Messages (optional)"
            hint="Give a number and Nokware sends two messages: when your report is received and when it is resolved. The department never sees your number, and it is deleted 30 days after the case closes."
          >
            <NumberFields contact={contact} onChange={setContact} sensitive={false} />
          </FormSection>
          <Note testId="report-civic-routing">
            An AI model reads your description to choose the department responsible, and Nokware sends it there. The
            department sees what you write and your photos, never your number. Other residents will see that a report
            about this topic in this area exists and can add their voice; your words, photos and number are never shown.
          </Note>
          <FormActions busy={filing.isPending} error={filing.error} onBack={onBack} />
        </form>
      </CardContent>
    </Card>
  );
}
