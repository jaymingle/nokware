import { PetitionsQueue } from "@/components/mce/petitions-queue";
import { RolePage } from "@/components/portal/role-page";

export default function McePetitionsPage() {
  return (
    <RolePage
      eyebrow="Oversight · Metropolitan Chief Executive"
      title="Petitions"
      lead="Every public petition, and where each one stands. A petition that reaches its signatures comes to you, and you have 30 days to answer it publicly: the Assembly will act, it's referred to a department, or it can't act, and why. Nobody here approves or removes a petition — residents publish, and contributors take one down on a named ground. Every response is written to the audit trail with your name and the time."
    >
      <PetitionsQueue />
    </RolePage>
  );
}
