import { FileRedirect } from "@/components/documents/file-redirect";

import type { Metadata } from "next";

export const metadata: Metadata = { title: "Opening PDF" };

export default async function FilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FileRedirect id={id} />;
}
