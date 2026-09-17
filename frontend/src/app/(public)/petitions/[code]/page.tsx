import { PetitionPage } from "@/components/petitions/petition-page";
import { env } from "@/lib/env";

import type { PetitionDetail } from "@/lib/api/types";
import type { Metadata } from "next";

type Params = Promise<{ code: string }>;

const DESCRIPTION_MAX = 200;

/** The petition itself, for the preview a shared link shows; nothing if it can't be read. */
async function petitionFor(code: string): Promise<PetitionDetail | null> {
  try {
    const response = await fetch(`${env.apiUrl}/api/petitions/${encodeURIComponent(code)}`, { next: { revalidate: 300 } });
    return response.ok ? ((await response.json()) as PetitionDetail) : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { code } = await params;
  const petition = await petitionFor(code);
  if (!petition) return { title: "Petition" };
  const description = petition.body.length > DESCRIPTION_MAX ? `${petition.body.slice(0, DESCRIPTION_MAX).trimEnd()}…` : petition.body;
  const title = `Petition: ${petition.title}`;
  return { title, description, openGraph: { title, description, type: "article", siteName: "Nokware" } };
}

export default async function Page({ params }: { params: Params }) {
  const { code } = await params;
  return <PetitionPage code={code} />;
}
