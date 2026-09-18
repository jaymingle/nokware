// A phone photo is 3 to 12 MB, and the API re-encodes every one of them to 2048px JPEG the moment it arrives. On a
// mobile connection in Accra the difference is minutes of uploading nobody sees the benefit of, so the shrinking
// happens here, before it is sent. The numbers match app/services/report_photos.py (MAX_EDGE, JPEG_QUALITY) so the
// server has nothing left to do; if it ever changes them, the worst case is a photo sent slightly larger.
import { PHOTO_TYPES } from "@/lib/report/photos";

export const MAX_EDGE = 2048;
export const QUALITY = 0.85;

/** The size to draw at, never larger than the photo itself. */
export function fitInside(width: number, height: number, edge = MAX_EDGE): { width: number; height: number } {
  const scale = Math.min(1, edge / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

function renamed(name: string): string {
  return `${name.replace(/\.[^.]+$/, "")}.jpg`;
}

async function encode(bitmap: ImageBitmap): Promise<Blob | null> {
  const { width, height } = fitInside(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.drawImage(bitmap, 0, 0, width, height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", QUALITY));
}

/**
 * The photo as it will be stored: at most 2048px on its long side, drawn the way up it was taken.
 *
 * Drawing it through a canvas also leaves EXIF behind — the camera's GPS among it — so a photo of somewhere
 * someone is hiding doesn't travel with the place attached. The server strips it too; this is one step earlier.
 *
 * Anything that can't be read here is sent as it is: refusing a photo the API might accept would be the browser
 * overruling the only code that knows the rules.
 */
export async function shrink(file: File): Promise<File> {
  if (!PHOTO_TYPES.includes(file.type) || typeof createImageBitmap !== "function") return file;
  let bitmap: ImageBitmap | null = null;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const smaller = bitmap.width > MAX_EDGE || bitmap.height > MAX_EDGE;
    const blob = await encode(bitmap);
    if (!blob || (!smaller && blob.size >= file.size)) return file;
    return new File([blob], renamed(file.name), { type: "image/jpeg", lastModified: file.lastModified });
  } catch {
    return file;
  } finally {
    bitmap?.close();
  }
}
