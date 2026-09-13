/** What the citizen filled in, from either form. */
export type ReportDraft = {
  description: string;
  ward?: string;
  subMetro?: string;
  safetyTopic?: string; // set only by the personal-safety form
  phone: string;
  whatsapp: string;
  notify: boolean; // safety form only: the citizen's opt-in to messages
  callbackConsent: boolean; // safety form only
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
  if (safety) {
    form.set("safety_topic", draft.safetyTopic ?? "");
    form.set("notify", String(draft.notify));
    form.set("callback_consent", String(draft.callbackConsent));
  }
  if (!safety || draft.notify || draft.callbackConsent) {
    setIfGiven(form, "phone", draft.phone);
    setIfGiven(form, "whatsapp", draft.whatsapp);
  }
  draft.photos.forEach((photo) => form.append("photos", photo));
  return form;
}
