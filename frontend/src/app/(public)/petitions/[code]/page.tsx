import { PetitionPage } from "@/components/petitions/petition-page";
import { env } from "@/lib/env";

import type { PetitionOrTombstone } from "@/lib/api/types";
import type { Metadata } from "next";

type Params = Promise<{ code: string }>;

const DESCRIPTION_MAX = 200;

/** For the preview a shared link shows. A removed petition answers here too, as its tombstone. */
async function petitionFor(code: string): Promise<PetitionOrTombstone | null> {
  try {
    const response = await fetch(`${env.apiUrl}/api/petitions/${encodeURIComponent(code)}`, { next: { revalidate: 300 } });
    return response.ok ? ((await response.json()) as PetitionOrTombstone) : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { code } = await params;
  const petition = await petitionFor(code);
  if (!petition) return { title: "Petition" };
  // A removed petition's link must preview as the removal, never as the petition: a shared card carrying the
  // title and the first words would be the petition still in circulation after it came down.
  if (petition.state === "removed") {
    return { title: "Petition removed", description: `This petition was removed: ${petition.ground_words.toLowerCase()}.` };
  }
  const description = petition.body.length > DESCRIPTION_MAX ? `${petition.body.slice(0, DESCRIPTION_MAX).trimEnd()}…` : petition.body;
  const title = `Petition: ${petition.title}`;
  return { title, description, openGraph: { title, description, type: "article", siteName: "Nokware" } };
}

export default async function Page({ params }: { params: Params }) {
  const { code } = await params;
  return <PetitionPage code={code} />;
}
