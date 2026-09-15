import type { Metadata } from "next";

import { RtiPage } from "@/components/rti/rti-page";

export const metadata: Metadata = {
  title: "Request a document",
  description: "How to request a document the Accra Metropolitan Assembly hasn't published, under the Right to Information Act, 2019.",
};

type Search = Promise<{ [key: string]: string | string[] | undefined }>;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Page({ searchParams }: { searchParams: Search }) {
  const params = await searchParams;
  return <RtiPage document={one(params.document)} period={one(params.period)} elsewhere={one(params.elsewhere) === "1"} />;
}
