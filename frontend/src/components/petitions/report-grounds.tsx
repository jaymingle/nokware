import type { PetitionGround, PetitionGroundOption } from "@/lib/api/types";

/** What a report is and isn't, said before anyone sends one. The same four grounds judge a petition and a comment. */
export function reportHidesNothing(subject: "petition" | "comment"): string {
  return `Reporting hides nothing. The ${subject} stays up, exactly as it is, while a contributor reads what you send.`;
}

type Props = {
  grounds: PetitionGroundOption[];
  chosen: PetitionGround;
  onChoose: (ground: PetitionGround) => void;
  /** Distinct per thing reported: two dialogs on one page must never be one group of radios. */
  name: string;
  testIdPrefix: string;
};

export function ReportGrounds({ grounds, chosen, onChoose, name, testIdPrefix }: Props) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-1.5 text-[14px] font-medium">Why are you reporting it?</legend>
      {grounds.map((ground) => (
        <label key={ground.id} className="flex items-center gap-2.5 text-[14px]">
          <input type="radio" name={name} checked={chosen === ground.id} onChange={() => onChoose(ground.id)}
            className="size-4 accent-teal" data-testid={`${testIdPrefix}-${ground.id}`} />
          {ground.label}
        </label>
      ))}
    </fieldset>
  );
}
