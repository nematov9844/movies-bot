"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Sidebar } from "@/components/sidebar";
import { decodeAccessToken, getAccessToken } from "@/lib/auth";
import type { AdminRole } from "@/lib/types";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [role, setRole] = useState<AdminRole | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    const payload = decodeAccessToken(token);
    setRole(payload?.role ?? null);
    setChecked(true);
  }, [router]);

  if (!checked) return null;

  return (
    <div className="flex min-h-screen">
      <Sidebar role={role} />
      <main className="flex-1 overflow-y-auto bg-muted/20 p-6">{children}</main>
    </div>
  );
}
