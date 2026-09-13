import { apiRequest } from "@/lib/api/client";

import type { Me } from "@/lib/api/types";

export function getMe(): Promise<Me> {
  return apiRequest<Me>("/api/me");
}
