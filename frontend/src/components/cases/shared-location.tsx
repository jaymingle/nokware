"use client";

import { MapPinIcon } from "lucide-react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { useOpenLocation } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/time";

import type { CaseDetail, SharedLocationView } from "@/lib/api/types";

function mapsLink(location: SharedLocationView): string | null {
  if (location.latitude === null || location.longitude === null) return null;
  return `https://www.google.com/maps/search/?api=1&query=${location.latitude},${location.longitude}`;
}

function Place({ location, testId }: { location: SharedLocationView; testId: string }) {
  const map = mapsLink(location);
  return (
    <div className="flex flex-col gap-1" data-testid={`${testId}-place`}>
      {location.address ? <p className="text-[14px] break-words text-ink">{location.address}</p> : null}
      {map ? (
        <a href={map} target="_blank" rel="noreferrer" className="w-fit text-teal underline-offset-2 hover:underline" data-testid={`${testId}-map`}>
          Open the pin in maps ({location.latitude}, {location.longitude})
        </a>
      ) : null}
    </div>
  );
}

/** A precise location a safety reporter chose to share so help can come: opened on purpose, recorded, and told to them. */
export function SharedLocation({ detail }: { detail: CaseDetail }) {
  const open = useOpenLocation();
  if (!detail.location_shared_at) return null;
  const testId = `case-location-${detail.case_id}`;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-brick/30 px-3.5 py-3 text-[13px]" data-testid={testId}>
      <p className="flex items-center gap-1.5 font-medium">
        <MapPinIcon aria-hidden className="size-4 text-brick" />
        The citizen shared a precise location on {formatDateTime(detail.location_shared_at)} so help can come
      </p>
      <p className="text-ink-soft">
        Only the Police and Social Welfare on this case can open it. Each view is recorded in the chain of custody, and
        the citizen sees on their status page that it was viewed.
      </p>
      {open.data ? (
        <Place location={open.data} testId={testId} />
      ) : (
        <Button variant="secondary" size="sm" className="w-fit" disabled={open.isPending} onClick={() => open.mutate(detail.case_id)} data-testid={`${testId}-open`}>
          {open.isPending ? "Opening…" : "Show location"}
        </Button>
      )}
      {open.error ? <ErrorNote testId={`${testId}-error`}>{open.error.message}</ErrorNote> : null}
    </div>
  );
}
