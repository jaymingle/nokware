import { PetitionReports } from "@/components/contributor/petition-reports";
import { RolePage } from "@/components/portal/role-page";

export default function ContributorPetitionReportsPage() {
  return (
    <RolePage
      title="Reported petitions"
      lead="Petitions readers have reported, newest first. A petition can come down only on one of the four grounds, and only from a contributor who neither started nor signed it — so you confirm your number before you remove one. Anything else, leave up. Every removal is written to the audit trail with your name and the time."
    >
      <PetitionReports />
    </RolePage>
  );
}
