import { FormField } from "@/components/documents/document-fields";
import { Textarea } from "@/components/ui/textarea";

type DescriptionFieldProps = { min: number; max: number; placeholder: string; hint: string; sensitive: boolean };

export function DescriptionField({ min, max, placeholder, hint, sensitive }: DescriptionFieldProps) {
  return (
    <FormField id="description" label="What is happening?" hint={hint}>
      <Textarea
        id="description"
        name="description"
        required
        minLength={min}
        maxLength={max}
        rows={5}
        placeholder={placeholder}
        autoComplete={sensitive ? "off" : undefined}
        aria-describedby="description-hint"
        className="min-h-32"
        data-testid="report-description"
      />
    </FormField>
  );
}
