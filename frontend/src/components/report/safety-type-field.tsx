"use client";

import type { SafetyType } from "@/lib/api/types";

type SafetyTypeFieldProps = { types: SafetyType[]; value: string; onChange: (id: string) => void };

/** The citizen says what kind of danger it is; that alone decides who receives it. */
export function SafetyTypeField({ types, value, onChange }: SafetyTypeFieldProps) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1.5 text-[12.5px] text-ink-soft">What is happening?</legend>
      {types.map((type) => (
        <label
          key={type.id}
          className="flex cursor-pointer items-start gap-3 rounded-lg border bg-card px-3.5 py-3 transition-colors has-checked:border-teal has-checked:bg-teal-tint"
        >
          <input
            type="radio"
            name="safety_topic"
            value={type.id}
            required
            checked={value === type.id}
            onChange={() => onChange(type.id)}
            className="mt-1 size-4 shrink-0 accent-teal"
            data-testid={`report-safety-type-${type.id}`}
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-[14.5px]">{type.label}</span>
            <span className="text-[12.5px] text-ink-soft">{type.guide}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
