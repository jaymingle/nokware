import { PublishingRecordPage } from "@/components/accountability/publishing-record-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "What the Assembly publishes",
  description: "The documents the Accra Metropolitan Assembly is required to publish, against what The Ledger holds, by year.",
};

export default function Page() {
  return <PublishingRecordPage />;
}
