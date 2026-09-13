import type { Metadata } from "next";

import { StatusPage } from "@/components/report/status-page";

export const metadata: Metadata = {
  title: "Report status",
  description: "Follow a report to the Accra Metropolitan Assembly with its reference.",
};

export default function Page() {
  return <StatusPage />;
}
