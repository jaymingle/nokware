import { DirectoryPage } from "@/components/contacts/directory-page";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Who to call",
  description: "Emergency lines, the Accra Metropolitan Assembly and the services that act on reports, each with its source.",
};

export default function Page() {
  return <DirectoryPage />;
}
