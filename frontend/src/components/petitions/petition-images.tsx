"use client";

import { XIcon } from "lucide-react";
import Image from "next/image";

import { PhotoField } from "@/components/report/photo-field";

import type { ReportPhoto } from "@/lib/report/photos";

/**
 * The API takes a petition's images as files on the same form as its words, and gives no byte limit of its own in
 * /api/petitions/options. It applies the report's limit to them, so the page says the same number; the server
 * checks again, and shrink() has already brought a phone photo well under it.
 */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** An image the petition already shows: the stored name an edit keeps it by, and the link it is shown from. */
export type KeptImage = { id: string; url: string };

export function keptImages(ids: string[], urls: string[]): KeptImage[] {
  return ids.map((id, index) => ({ id, url: urls[index] })).filter((image) => Boolean(image.url));
}

function Kept({ images, onRemove }: { images: KeptImage[]; onRemove: (id: string) => void }) {
  if (images.length === 0) return null;
  return (
    <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" data-testid="petition-images-kept">
      {images.map((image, index) => (
        <li key={image.id} className="relative">
          <Image src={image.url} alt={`Photo ${index + 1} on this petition`} width={160} height={120} unoptimized
            className="aspect-4/3 w-full rounded-md border object-cover" />
          <button type="button" onClick={() => onRemove(image.id)} aria-label={`Remove photo ${index + 1}`}
            className="absolute top-1 right-1 grid size-7 place-items-center rounded-md bg-ink/80 text-paper hover:bg-ink"
            data-testid={`petition-images-kept-remove-${index}`}>
            <XIcon className="size-4" />
          </button>
        </li>
      ))}
    </ul>
  );
}

type FieldProps = {
  added: ReportPhoto[];
  onAdded: (added: ReportPhoto[]) => void;
  max: number;
  /** Only an edit has images already: a new petition has nothing to keep. */
  kept?: KeptImage[];
  onKept?: (kept: KeptImage[]) => void;
};

/**
 * The photos on a petition, on the form that starts one and on the form that edits it. An edit sends the stored
 * names it keeps and the new files together, so removing one here is what drops it from the next version.
 */
export function PetitionImageField({ added, onAdded, max, kept = [], onKept }: FieldProps) {
  const room = Math.max(0, max - kept.length);
  return (
    <div className="flex flex-col gap-2" data-testid="petition-images">
      <Kept images={kept} onRemove={(id) => onKept?.(kept.filter((image) => image.id !== id))} />
      <PhotoField photos={added} onChange={onAdded} name="petition" label="Photos (optional)"
        limits={{ maxPhotos: room, maxBytes: MAX_IMAGE_BYTES }}
        hint="The petition is public, so is anything in a photo. Location and camera details are removed before they are stored." />
    </div>
  );
}
