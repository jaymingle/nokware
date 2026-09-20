import { redirect } from "next/navigation";

// Kept because links to it exist in the wild; the record itself now lives at /accountability.
export default function Page() {
  redirect("/accountability");
}
