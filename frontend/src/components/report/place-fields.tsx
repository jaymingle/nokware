import { FormField } from "@/components/documents/document-fields";
import { NativeSelect, NativeSelectOptGroup, NativeSelectOption } from "@/components/ui/native-select";

import type { SubMetroOption } from "@/lib/api/types";

export function WardField({ subMetros }: { subMetros: SubMetroOption[] }) {
  return (
    <FormField id="ward" label="Where is it?" hint="The electoral area. Name the street or a landmark in your description.">
      <NativeSelect id="ward" name="ward" required defaultValue="" aria-describedby="ward-hint" className="w-full" data-testid="report-ward">
        <NativeSelectOption value="" disabled>
          Choose an electoral area
        </NativeSelectOption>
        {subMetros.map((subMetro) => (
          <NativeSelectOptGroup key={subMetro.id} label={`${subMetro.name} sub-metro`}>
            {subMetro.wards.map((ward) => (
              <NativeSelectOption key={ward.id} value={ward.id}>
                {ward.name}
              </NativeSelectOption>
            ))}
          </NativeSelectOptGroup>
        ))}
      </NativeSelect>
    </FormField>
  );
}

/** A safety report's place: a sub-metro at most, or none. */
export function SubMetroField({ subMetros }: { subMetros: SubMetroOption[] }) {
  return (
    <FormField id="sub_metro" label="Which part of Accra? (optional)" hint="Only the sub-metro is kept: never a street, area or address.">
      <NativeSelect id="sub_metro" name="sub_metro" defaultValue="" aria-describedby="sub_metro-hint" className="w-full" data-testid="report-sub-metro">
        <NativeSelectOption value="">Prefer not to say</NativeSelectOption>
        {subMetros.map((subMetro) => (
          <NativeSelectOption key={subMetro.id} value={subMetro.id}>
            {subMetro.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </FormField>
  );
}
