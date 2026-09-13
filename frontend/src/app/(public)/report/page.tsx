import type { Metadata } from "next";

import { ReportPage } from "@/components/report/report-page";

// The title stays neutral on every step, the safety form included.
export const metadata: Metadata = {
  title: "Report an issue",
  description: "Tell the Accra Metropolitan Assembly about a problem in your area, and follow it with your reference.",
};

export default function Page() {
  return <ReportPage />;
}
