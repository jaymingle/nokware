import { PublishingRecordPage } from "@/components/accountability/publishing-record-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "What the Assembly publishes",
  description: "The documents the Accra Metropolitan Assembly is required to publish, against what The Ledger holds, by year.",
};

// The publishing record is what Accountability means first: a hub of two cards made everyone choose before they
// had read anything. The responsiveness view is one card away, at the top of this page.
export default function Page() {
  return <PublishingRecordPage />;
}
