// Named aliases for the API's schemas. schema.d.ts is generated from the
// backend's OpenAPI document by `npm run api:types`; never edit it by hand.
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeResponse"];
export type Role = Schemas["Role"];
