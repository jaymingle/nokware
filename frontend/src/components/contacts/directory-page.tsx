"use client";

import { ContactItem } from "@/components/contacts/contact-item";
import { WhoRepresentsYou } from "@/components/contacts/who-represents-you";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { EmergencyNote } from "@/components/report/notes";
import { useContacts } from "@/lib/api/public-queries";
import { TIERS } from "@/lib/contacts";
import { formatDate } from "@/lib/time";

import type { ContactDirectory } from "@/lib/api/types";

export function TierKey() {
  return (
    <section aria-labelledby="tiers" className="flex flex-col gap-3">
      <h2 id="tiers" className="text-[19px]">How far each number can be trusted</h2>
      <ol className="grid gap-3 md:grid-cols-3">
        {TIERS.map((tier) => (
          <li key={tier.tier} className="rounded-xl border bg-card p-4">
            <div className="font-heading text-[15px] text-teal tabular-nums">Tier {tier.tier}</div>
            <div className="mt-1 text-[14.5px] font-medium">{tier.title}</div>
            <p className="mt-1 text-[13px] text-ink-soft">{tier.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Services({ directory }: { directory: ContactDirectory }) {
  return (
    <div className="flex flex-col gap-5">
      {directory.services.map((service) => (
        <section key={service.id} aria-labelledby={`service-${service.id}`} className="rounded-xl border bg-card px-5 py-3" data-testid={`directory-${service.id}`}>
          <h2 id={`service-${service.id}`} className="pt-1 text-[21px]">{service.name}</h2>
          <ul className="flex flex-col divide-y">
            {service.contacts.map((contact) => (
              <ContactItem key={contact.id} contact={contact} />
            ))}
          </ul>
        </section>
      ))}
      <p className="text-[12.5px] text-ink-soft">
        Numbers checked against their sources on {formatDate(directory.checked)}. Offices are listed by desk: no
        official is named beside a number.
      </p>
    </div>
  );
}

/** Every number, grouped by service, each with its source. */
export function DirectoryPage() {
  const directory = useContacts();
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
      <PageIntro eyebrow="Contacts" title="Who to call">
        Emergency lines, the Assembly, the services that act on reports, and who represents your area. Every number
        shows where it comes from, the same way Ask shows the source of every answer.
      </PageIntro>
      <EmergencyNote />
      <WhoRepresentsYou />
      <TierKey />
      {directory.isPending ? <LoadingPanel label="Loading the numbers…" /> : null}
      {directory.error ? <ErrorPanel message={directory.error.message} onRetry={() => directory.refetch()} /> : null}
      {directory.data ? <Services directory={directory.data} /> : null}
    </div>
  );
}
