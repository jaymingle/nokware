import { StatusPage } from "@/components/report/status-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Report status",
  description: "Follow a report to the Accra Metropolitan Assembly with its reference.",
};

export default function Page() {
  return <StatusPage />;
}
