const PRINCIPLES = [
  {
    title: "Every answer carries its source",
    body: "Ask answers only from documents in the Ledger and cites each one: who published it, and a link to the PDF.",
  },
  {
    title: "Nothing reaches the public unsigned",
    body: "Documents come from Assembly departments, or from verified contributors whose submissions the department reviews first.",
  },
  {
    title: "Silence is stated, not filled",
    body: "Where the Ledger holds nothing on a question, Nokware says so, and points to your right to request the information.",
  },
];

/** How the record stays trustworthy, in three lines. */
export function Principles() {
  return (
    <section aria-labelledby="principles" className="flex flex-col gap-5">
      <h2 id="principles" className="text-[26px]">
        How the record stays honest
      </h2>
      <ol className="grid gap-4 md:grid-cols-3">
        {PRINCIPLES.map((principle, index) => (
          <li key={principle.title} className="flex flex-col gap-1.5 border-t border-hairline pt-4">
            <span className="font-heading text-[15px] text-teal tabular-nums">0{index + 1}</span>
            <h3 className="text-[17px] leading-snug">{principle.title}</h3>
            <p className="text-[14px] text-ink-soft">{principle.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
