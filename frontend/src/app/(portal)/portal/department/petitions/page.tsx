import { SharedPetitions } from "@/components/department/shared-petitions";
import { RolePage } from "@/components/portal/role-page";

export default function DepartmentPetitionsPage() {
  return (
    <RolePage
      title="Petitions shared with you"
      lead="Petitions the MCE has asked your department to answer, newest first. Your department writes one note on each, published on the petition's public page under the department's name and never under yours. It can't be changed afterwards, and it isn't the MCE's response: that is the MCE's to give."
    >
      <SharedPetitions />
    </RolePage>
  );
}
