import { RtiPage } from "@/components/rti/rti-page";
import { firstParam, type SearchParams } from "@/lib/search-params";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Request a document",
  description: "How to request a document the Accra Metropolitan Assembly hasn't published, under the Right to Information Act, 2019.",
};

export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  return <RtiPage document={firstParam(params.document)} period={firstParam(params.period)} elsewhere={firstParam(params.elsewhere) === "1"} />;
}
