"use client";

import { useState } from "react";

import { ContactList } from "@/components/contacts/contact-list";
import { NumberFields, SafetyConsents } from "@/components/report/contact-fields";
import { DescriptionField } from "@/components/report/description-field";
import { FormActions, FormSection } from "@/components/report/form-parts";
import { Note } from "@/components/report/notes";
import { PhotoField } from "@/components/report/photo-field";
import { SubMetroField } from "@/components/report/place-fields";
import { SafetyTypeField } from "@/components/report/safety-type-field";
import { Card, CardContent } from "@/components/ui/card";
import { useReportForm } from "@/hooks/use-report-form";
import { joinNames } from "@/lib/text";

import type { ReportFormProps } from "@/components/report/civic-form";
import type { SafetyType } from "@/lib/api/types";

function WhoReceives({ type }: { type: SafetyType }) {
  return (
    <Note tone="private" testId="report-safety-routing">
      This goes only to {joinNames(type.recipients)}. It is never shown on the public dashboard, and it is not read by
      an AI model.
    </Note>
  );
}

/** Someone's safety: the citizen names the danger, so the report goes straight to its services, privately. */
export function SafetyForm({ options, onFiled, onBack }: ReportFormProps) {
  const { photos, setPhotos, contact, setContact, submit, filing } = useReportForm(onFiled);
  const [topic, setTopic] = useState("");
  const chosen = options.safety_types.find((type) => type.id === topic);
  const limits = { maxPhotos: options.max_photos, maxBytes: options.max_photo_bytes };
  return (
    <Card>
      <CardContent className="py-2 sm:px-6 sm:py-4">
        <form onSubmit={(event) => submit(event, topic)} autoComplete="off" className="flex flex-col gap-6" data-testid="report-safety-form">
          <ContactList
            title="Need help now?"
            lead="If someone is in danger, call one of these first. This form is not watched around the clock."
            contacts={options.safety_contacts}
            testId="report-safety-contacts"
            directoryLink={false}
            columns
          />
          <SafetyTypeField types={options.safety_types} value={topic} onChange={setTopic} />
          {chosen ? <WhoReceives type={chosen} /> : null}
          <DescriptionField
            min={options.description_min}
            max={options.description_max}
            placeholder="Say what is happening, as much as you feel safe to share."
            hint="Only the services it goes to will read this."
            sensitive
          />
          <SubMetroField subMetros={options.sub_metros} />
          <PhotoField photos={photos} onChange={setPhotos} limits={limits} hint="Only if it is safe to do so. Location and camera details are removed." />
          <FormSection
            title="A number (optional)"
            hint="Give one only if it is safe for you to be messaged or called on it. It is kept apart from your report and deleted 30 days after the case closes."
          >
            <NumberFields contact={contact} onChange={setContact} sensitive />
            <SafetyConsents contact={contact} onChange={setContact} />
          </FormSection>
          <FormActions busy={filing.isPending} error={filing.error} onBack={onBack} />
        </form>
      </CardContent>
    </Card>
  );
}
