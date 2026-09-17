"use client";

import { useState, type FormEvent } from "react";

import { useFileReport } from "@/lib/api/public-queries";
import { NO_CONTACT, reportFormData, type Contact } from "@/lib/report/form";

import type { ReportReceipt } from "@/lib/api/types";
import type { ReportPhoto } from "@/lib/report/photos";

function text(fields: FormData, name: string): string | undefined {
  const value = fields.get(name);
  return typeof value === "string" ? value : undefined;
}

/** Photos and numbers are held here; the text fields are read from the form when it is sent. */
export function useReportForm(onFiled: (receipt: ReportReceipt) => void) {
  const filing = useFileReport();
  const [photos, setPhotos] = useState<ReportPhoto[]>([]);
  const [contact, setContact] = useState<Contact>(NO_CONTACT);
  const submit = (event: FormEvent<HTMLFormElement>, safetyTopic?: string) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const form = reportFormData({
      ...contact,
      description: text(fields, "description") ?? "",
      ward: text(fields, "ward"),
      subMetro: text(fields, "sub_metro"),
      safetyTopic,
      photos: photos.map((photo) => photo.file),
    });
    filing.mutate(form, { onSuccess: onFiled });
  };
  return { photos, setPhotos, contact, setContact, submit, filing };
}
