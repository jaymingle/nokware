import { PetitionListPage } from "@/components/petitions/petition-list-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Petitions",
  description: "Residents asking the Accra Metropolitan Assembly to act, the support each has gathered, and how the MCE has handled them.",
};

export default function Page() {
  return <PetitionListPage />;
}
