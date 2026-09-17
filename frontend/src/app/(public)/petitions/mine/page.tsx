import { MyPetitionsPage } from "@/components/petitions/my-petitions-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Your petitions",
  description: "The petitions you started, and any decision the MCE made on them.",
};

export default function Page() {
  return <MyPetitionsPage />;
}
