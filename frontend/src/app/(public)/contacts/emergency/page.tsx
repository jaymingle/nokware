import { EmergencyPage } from "@/components/contacts/emergency-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Help now",
  description: "Emergency numbers for Accra: police, fire, ambulance, NADMO and Social Welfare, each with its source.",
};

export default function Page() {
  return <EmergencyPage />;
}
