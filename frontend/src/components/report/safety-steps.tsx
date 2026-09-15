/** What to do right now, after the numbers to call: the same steps as WhatsApp and USSD, from the API. */
export function SafetySteps({ steps, testId }: { steps: string[]; testId: string }) {
  if (steps.length === 0) return null;
  return (
    <section className="flex flex-col gap-1.5 rounded-xl border bg-paper-subtle px-4 py-3" data-testid={testId}>
      <h3 className="text-[17px]">What to do now</h3>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-[14px]">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
    </section>
  );
}
