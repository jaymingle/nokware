import { PetitionResponses } from "@/components/mce/petition-responses";
import { PetitionReview } from "@/components/mce/petition-review";
import { RolePage } from "@/components/portal/role-page";

export default function McePetitionsPage() {
  return (
    <RolePage
      eyebrow="Oversight · Metropolitan Chief Executive"
      title="Petitions"
      lead="Petitions residents have sent for review. Publish one, or refuse it for one of the fixed reasons. If you don't decide within 72 hours, it publishes automatically, and the public petitions page counts every refusal by its reason. Every decision is written to the audit trail with your name and the time."
    >
      <PetitionReview />
      <PetitionResponses />
    </RolePage>
  );
}
