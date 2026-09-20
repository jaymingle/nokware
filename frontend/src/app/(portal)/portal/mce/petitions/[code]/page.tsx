import { McePetition } from "@/components/mce/petition-detail";
import { PageShell } from "@/components/page-shell";

import type { Metadata } from "next";

type Params = Promise<{ code: string }>;

export const metadata: Metadata = { title: "Petition" };

export default async function McePetitionPage({ params }: { params: Params }) {
  const { code } = await params;
  return (
    <PageShell width="data" eyebrow="Oversight · Metropolitan Chief Executive" title="Petition">
      <McePetition code={code} />
    </PageShell>
  );
}
