import { formatBytes } from "@/lib/uploads";

// The API re-encodes each photo from its pixels alone; these are the formats it reads.
export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

export type PhotoLimits = { maxPhotos: number; maxBytes: number };

export type PhotoPick = { photos: File[]; problem: string | null };

function photoProblem(file: Pick<File, "name" | "type" | "size">, limits: PhotoLimits): string | null {
  if (!PHOTO_TYPES.includes(file.type)) return `${file.name} isn't a JPEG, PNG or WebP photo.`;
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > limits.maxBytes) return `${file.name} is ${formatBytes(file.size)}; each photo can be up to ${formatBytes(limits.maxBytes)}.`;
  return null;
}

/** Adds the chosen photos to those already attached, keeping only those the API will take. */
export function addPhotos(current: File[], chosen: File[], limits: PhotoLimits): PhotoPick {
  const problems: string[] = [];
  const photos = [...current];
  for (const file of chosen) {
    const problem = photoProblem(file, limits);
    if (problem) problems.push(problem);
    else if (photos.length >= limits.maxPhotos) {
      problems.push(`You can attach up to ${limits.maxPhotos} photos.`);
      break;
    } else photos.push(file);
  }
  return { photos, problem: problems.length ? problems.join(" ") : null };
}
