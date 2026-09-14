"use client";

import { Services, TierKey } from "@/components/contacts/directory-page";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { useContacts } from "@/lib/api/public-queries";
import { EMERGENCY_SERVICES } from "@/lib/contacts";

import type { ContactDirectory } from "@/lib/api/types";

function emergencyOnly(directory: ContactDirectory): ContactDirectory {
  return { ...directory, services: directory.services.filter((service) => EMERGENCY_SERVICES.includes(service.id)) };
}

/** Emergency numbers only: where an SMS or USSD screen sends someone who needs help now. */
export function EmergencyPage() {
  const directory = useContacts();
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
      <PageIntro eyebrow="Contacts" title="Help now">
        If someone is in danger, call. Emergency lines in Ghana often don&apos;t connect, so every number we have is
        here: if one doesn&apos;t answer, try the next. For someone ill or hurt, call an ambulance on 193 or 112.
      </PageIntro>
      {directory.isPending ? <LoadingPanel label="Loading the numbers…" /> : null}
      {directory.error ? <ErrorPanel message={directory.error.message} onRetry={() => directory.refetch()} /> : null}
      {directory.data ? <Services directory={emergencyOnly(directory.data)} /> : null}
      <TierKey />
    </div>
  );
}
