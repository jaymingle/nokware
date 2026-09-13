function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name} is not set. Add it to frontend/.env.local (see .env.example).`);
  }
  return value;
}

// NEXT_PUBLIC_* values must be read by their literal names so Next.js can
// inline them into the browser bundle at build time.
export const env = {
  apiUrl: required("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL),
  appwriteEndpoint: required("NEXT_PUBLIC_APPWRITE_ENDPOINT", process.env.NEXT_PUBLIC_APPWRITE_ENDPOINT),
  appwriteProjectId: required("NEXT_PUBLIC_APPWRITE_PROJECT_ID", process.env.NEXT_PUBLIC_APPWRITE_PROJECT_ID),
};
