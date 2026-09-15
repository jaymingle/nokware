import type { Metadata } from "next";

import { AccountabilityHub } from "@/components/accountability/accountability-hub";

export const metadata: Metadata = {
  title: "Accountability",
  description: "What the Accra Metropolitan Assembly has published and what it hasn't, and how its departments respond to residents.",
};

export default function Page() {
  return <AccountabilityHub />;
}
