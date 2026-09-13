import { ReviewQueue } from "@/components/department/review-queue";
import { RolePage } from "@/components/portal/role-page";

export default function DepartmentReviewPage() {
  return (
    <RolePage
      title="Awaiting your review"
      lead="Documents contributors have submitted for your department. Each one publishes automatically when its clock runs out, unless you dispute it."
    >
      <ReviewQueue />
    </RolePage>
  );
}
