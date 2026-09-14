import { FEWER_THAN_FIVE, formatCount, type Count } from "@/lib/report/dashboard";

/** A report count: the number, or "<5" read out as "fewer than 5". */
export function CountValue({ value }: { value: Count }) {
  if (value !== null) return <>{formatCount(value)}</>;
  return (
    <abbr title={FEWER_THAN_FIVE} aria-label={FEWER_THAN_FIVE} className="no-underline">
      &lt;5
    </abbr>
  );
}
