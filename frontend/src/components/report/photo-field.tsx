"use client";

import Image from "next/image";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { ImagePlusIcon, XIcon } from "lucide-react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PHOTO_TYPES, addPhotos, type PhotoLimits, type ReportPhoto } from "@/lib/report/photos";
import { formatBytes } from "@/lib/uploads";

function Thumb({ photo, index, onRemove }: { photo: ReportPhoto; index: number; onRemove: () => void }) {
  return (
    <li className="relative">
      <Image src={photo.url} alt={`Photo ${index + 1}`} width={160} height={120} unoptimized className="aspect-4/3 w-full rounded-md border object-cover" />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove photo ${index + 1}`}
        className="absolute top-1 right-1 grid size-7 place-items-center rounded-md bg-ink/80 text-paper hover:bg-ink"
        data-testid={`report-photo-remove-${index}`}
      >
        <XIcon className="size-4" />
      </button>
    </li>
  );
}

/** Frees every preview when the form goes away (after filing, or on leaving the page). */
function useRevokeOnUnmount(photos: ReportPhoto[]) {
  const latest = useRef(photos);
  useEffect(() => {
    latest.current = photos;
  }, [photos]);
  useEffect(() => () => latest.current.forEach((photo) => URL.revokeObjectURL(photo.url)), []);
}

type PhotoFieldProps = { photos: ReportPhoto[]; onChange: (photos: ReportPhoto[]) => void; limits: PhotoLimits; hint: string };

/** Up to the limit of photos, previewed here and checked before they're sent. */
export function PhotoField({ photos, onChange, limits, hint }: PhotoFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useRevokeOnUnmount(photos);
  const choose = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = addPhotos(photos.map((photo) => photo.file), Array.from(event.target.files ?? []), limits);
    const added = picked.photos.slice(photos.length).map((file) => ({ file, url: URL.createObjectURL(file) }));
    onChange([...photos, ...added]);
    setProblem(picked.problem);
    event.target.value = ""; // choosing the same photo again still fires a change
  };
  const remove = (index: number) => {
    URL.revokeObjectURL(photos[index].url);
    onChange(photos.filter((_, i) => i !== index));
    setProblem(null);
  };
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="report-photos">Photos (optional)</Label>
      <p className="text-[12.5px] text-ink-soft">
        Up to {limits.maxPhotos} JPEG, PNG or WebP photos, {formatBytes(limits.maxBytes)} each. {hint}
      </p>
      {photos.length > 0 ? (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" data-testid="report-photos">
          {photos.map((photo, index) => (
            <Thumb key={photo.url} photo={photo} index={index} onRemove={() => remove(index)} />
          ))}
        </ul>
      ) : null}
      <input ref={input} id="report-photos" type="file" accept={PHOTO_TYPES.join(",")} multiple onChange={choose} className="sr-only" data-testid="report-photos-input" />
      <PhotoButtons count={photos.length} limits={limits} onAdd={() => input.current?.click()} />
      {problem ? <ErrorNote testId="report-photos-problem">{problem}</ErrorNote> : null}
    </div>
  );
}

function PhotoButtons({ count, limits, onAdd }: { count: number; limits: PhotoLimits; onAdd: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="button" variant="secondary" onClick={onAdd} disabled={count >= limits.maxPhotos} data-testid="report-photos-add">
        <ImagePlusIcon data-icon="inline-start" />
        {count ? "Add more photos" : "Add photos"}
      </Button>
      {count ? <span className="text-[12.5px] text-ink-soft">{count} of {limits.maxPhotos}</span> : null}
    </div>
  );
}
