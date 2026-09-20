import { NewPetitionPage } from "@/components/petitions/new-petition-page";
import { firstParam, type SearchParams } from "@/lib/search-params";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Start a petition",
  description: "Ask the Accra Metropolitan Assembly to act, and gather support for it.",
};

const ISSUE_ID = /^[a-z0-9]{6,20}$/;

function issueFrom(value: string | string[] | undefined): string | null {
  const one = firstParam(value);
  return one && ISSUE_ID.test(one) ? one : null;
}

export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  return <NewPetitionPage issue={issueFrom(params.issue)} />;
}
