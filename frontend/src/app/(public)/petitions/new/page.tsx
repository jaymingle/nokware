import { NewPetitionPage } from "@/components/petitions/new-petition-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Start a petition",
  description: "Ask the Accra Metropolitan Assembly to act, and gather support for it.",
};

type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const ISSUE_ID = /^[a-z0-9]{6,20}$/;

/** An issue linked from the issue list, if the address carries one that could be an issue's public ID. */
function issueFrom(value: string | string[] | undefined): string | null {
  const one = Array.isArray(value) ? value[0] : value;
  return one && ISSUE_ID.test(one) ? one : null;
}

export default async function Page({ searchParams }: { searchParams: Search }) {
  const params = await searchParams;
  return <NewPetitionPage issue={issueFrom(params.issue)} />;
}
