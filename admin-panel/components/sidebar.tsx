"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Film,
  Clapperboard,
  Users,
  Star,
  Radio,
  Megaphone,
  Settings,
  ScrollText,
  ShieldCheck,
  LogOut,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { clearTokens } from "@/lib/auth";
import { ThemeToggle } from "@/components/theme-toggle";
import type { AdminRole } from "@/lib/types";

const NAV_ITEMS: { href: string; label: string; icon: typeof LayoutDashboard; minRole?: AdminRole }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/movies", label: "Kinolar", icon: Film },
  { href: "/series", label: "Seriallar", icon: Clapperboard },
  { href: "/users", label: "Foydalanuvchilar", icon: Users },
  { href: "/premium", label: "Premium", icon: Star },
  { href: "/channels", label: "Kanallar", icon: Radio },
  { href: "/broadcast", label: "Broadcast", icon: Megaphone },
  { href: "/settings", label: "Sozlamalar", icon: Settings },
  { href: "/logs", label: "Loglar", icon: ScrollText },
  { href: "/admins", label: "Adminlar", icon: ShieldCheck, minRole: "owner" },
];

export function Sidebar({ role }: { role: AdminRole | null }) {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r bg-card">
      <div className="flex items-center justify-between border-b p-4">
        <span className="text-lg font-semibold">🎬 Admin Panel</span>
        <ThemeToggle />
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {NAV_ITEMS.filter((item) => !item.minRole || item.minRole === role).map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-2">
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <LogOut className="h-4 w-4" />
          Chiqish
        </button>
      </div>
    </aside>
  );
}
