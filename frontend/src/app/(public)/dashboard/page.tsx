import { DashboardPage } from "@/components/dashboard/dashboard-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "The city, in the aggregate",
  description: "What Accra's residents reported to the Assembly over the last twelve months, and what was resolved.",
};

export default function Page() {
  return <DashboardPage />;
}
