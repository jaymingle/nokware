"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useCategories, useDepartments } from "@/lib/api/queries";

import type { ReactNode } from "react";

export function FormField({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-[12.5px] text-ink-soft">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TitleField() {
  return (
    <FormField id="title" label="Title">
      <Input id="title" name="title" required minLength={3} maxLength={300} placeholder="e.g. 2026 Composite Budget" data-testid="field-title" />
    </FormField>
  );
}

export function CategoryField() {
  const { data: categories, isPending, error } = useCategories();
  return (
    <FormField id="category" label="Category" hint={error ? `Couldn't load categories: ${error.message}` : undefined}>
      <NativeSelect id="category" name="category" required defaultValue="" disabled={isPending} className="w-full" data-testid="field-category">
        <NativeSelectOption value="" disabled>
          {isPending ? "Loading categories…" : "Choose a category"}
        </NativeSelectOption>
        {categories?.map((category) => (
          <NativeSelectOption key={category.id} value={category.id}>
            {category.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </FormField>
  );
}

export function DepartmentField() {
  const { data: departments, isPending, error } = useDepartments();
  return (
    <FormField
      id="department"
      label="Department it belongs to"
      hint={error ? `Couldn't load departments: ${error.message}` : "That department reviews it before it can publish."}
    >
      <NativeSelect id="department" name="department" required defaultValue="" disabled={isPending} className="w-full" data-testid="field-department">
        <NativeSelectOption value="" disabled>
          {isPending ? "Loading departments…" : "Choose a department"}
        </NativeSelectOption>
        {departments?.map((department) => (
          <NativeSelectOption key={department.id} value={department.id}>
            {department.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </FormField>
  );
}

export function YearField() {
  const thisYear = new Date().getFullYear();
  return (
    <FormField id="document_year" label="Document year (optional)" hint="The year the document covers or was issued. Ask cites it.">
      <Input
        id="document_year"
        name="document_year"
        type="number"
        inputMode="numeric"
        min={1900}
        max={thisYear}
        placeholder={`e.g. ${thisYear}`}
        aria-describedby="document_year-hint"
        className="max-w-40"
        data-testid="field-year"
      />
    </FormField>
  );
}

export function SourceUrlField({ required, hint }: { required: boolean; hint: string }) {
  return (
    <FormField id="source_url" label={required ? "Source web address" : "Source web address (optional)"} hint={hint}>
      <Input
        id="source_url"
        name="source_url"
        type="url"
        required={required}
        maxLength={2048}
        placeholder="https://"
        aria-describedby="source_url-hint"
        data-testid="field-source-url"
      />
    </FormField>
  );
}
