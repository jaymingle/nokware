import type { Metadata } from "next";

import { PetitionListPage } from "@/components/petitions/petition-list-page";

export const metadata: Metadata = {
  title: "Petitions",
  description: "Residents asking the Accra Metropolitan Assembly to act, the support each has gathered, and how the MCE has handled them.",
};

export default function Page() {
  return <PetitionListPage />;
}
