import type { ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth/auth-context";

// Sign-in and the portal share one auth state; public pages don't load it.
export default function PortalGroupLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      {children}
      <Toaster position="bottom-right" />
    </AuthProvider>
  );
}
