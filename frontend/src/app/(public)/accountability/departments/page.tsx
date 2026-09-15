import type { Metadata } from "next";

import { ResponsivenessPage } from "@/components/accountability/responsiveness-page";

export const metadata: Metadata = {
  title: "How departments respond",
  description: "How each Assembly department handles residents' reports and contributors' documents, over the last twelve months.",
};

export default function Page() {
  return <ResponsivenessPage />;
}
