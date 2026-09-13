// Named aliases for the API's schemas. schema.d.ts is generated from the
// backend's OpenAPI document by `npm run api:types`; never edit it by hand.
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeResponse"];
export type Role = Schemas["Role"];
export type Action = Schemas["Action"];
/** Actions sent as JSON; resubmit carries a file and has its own endpoint. */
export type ReviewAction = Exclude<Action, "resubmit">;
export type DocumentOut = Schemas["DocumentOut"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type DocumentPage = Schemas["DocumentPage"];
export type HistoryEntry = Schemas["HistoryEntryOut"];
export type HistoryAction = Schemas["HistoryAction"];
export type IngestionState = Schemas["IngestionState"];
export type LedgerStatus = Schemas["LedgerStatus"];
export type FileLink = Schemas["FileLink"];
export type Option = Schemas["Option"];
