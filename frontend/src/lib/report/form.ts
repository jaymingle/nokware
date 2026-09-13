/** The citizen's numbers, and (safety form only) what they agreed they may be used for. */
export type Contact = { phone: string; whatsapp: string; notify: boolean; callbackConsent: boolean };

export const NO_CONTACT: Contact = { phone: "", whatsapp: "", notify: false, callbackConsent: false };

export function hasNumber(contact: Pick<Contact, "phone" | "whatsapp">): boolean {
  return Boolean(contact.phone.trim() || contact.whatsapp.trim());
}

/** What the citizen filled in, from either form. */
export type ReportDraft = Contact & {
  description: string;
  ward?: string;
  subMetro?: string;
  safetyTopic?: string; // set only by the personal-safety form
  photos: File[];
};

function setIfGiven(form: FormData, name: string, value: string | undefined) {
  const trimmed = value?.trim();
  if (trimmed) form.set(name, trimmed);
}

/**
 * The multipart body for POST /api/reports. On the safety form a number goes
 * only if the citizen agreed to messages or a call: otherwise there is no use
 * for it, and it isn't sent.
 */
export function reportFormData(draft: ReportDraft): FormData {
  const form = new FormData();
  form.set("description", draft.description.trim());
  setIfGiven(form, "ward", draft.ward);
  setIfGiven(form, "sub_metro", draft.subMetro);
  const safety = Boolean(draft.safetyTopic);
  const notify = draft.notify && hasNumber(draft);
  const callbackConsent = draft.callbackConsent && hasNumber(draft);
  if (safety) {
    form.set("safety_topic", draft.safetyTopic ?? "");
    form.set("notify", String(notify));
    form.set("callback_consent", String(callbackConsent));
  }
  if (!safety || notify || callbackConsent) {
    setIfGiven(form, "phone", draft.phone);
    setIfGiven(form, "whatsapp", draft.whatsapp);
  }
  draft.photos.forEach((photo) => form.append("photos", photo));
  return form;
}
