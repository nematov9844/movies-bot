"use client";

import { useCallback, useEffect, useState } from "react";
import { Ban, CheckCircle, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Page, PremiumPlan, UserRow } from "@/lib/types";

const PAGE_SIZE = 20;

export default function UsersPage() {
  const [data, setData] = useState<Page<UserRow> | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [grantTarget, setGrantTarget] = useState<UserRow | null>(null);
  const [plans, setPlans] = useState<PremiumPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<number | null>(null);
  const [granting, setGranting] = useState(false);

  const load = useCallback(() => {
    apiFetch<Page<UserRow>>("/api/users", { params: { page, size: PAGE_SIZE, q } })
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [page, q]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleBlock(user: UserRow) {
    await apiFetch(`/api/users/${user.id}/block`, {
      method: "PATCH",
      body: JSON.stringify({ blocked: !user.is_blocked }),
    });
    load();
  }

  async function openGrant(user: UserRow) {
    setGrantTarget(user);
    setSelectedPlan(null);
    if (plans.length === 0) {
      const list = await apiFetch<PremiumPlan[]>("/api/premium/plans");
      setPlans(list.filter((p) => p.is_active));
    }
  }

  async function onGrant(e: React.FormEvent) {
    e.preventDefault();
    if (!grantTarget || !selectedPlan) return;
    setGranting(true);
    try {
      await apiFetch("/api/premium/grant", {
        method: "POST",
        body: JSON.stringify({ user_id: grantTarget.id, plan_id: selectedPlan }),
      });
      setGrantTarget(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setGranting(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Foydalanuvchilar</h1>

      <Input
        placeholder="ID yoki username bo'yicha qidirish..."
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setPage(1);
        }}
        className="max-w-sm"
      />

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Username</TableHead>
              <TableHead>Ism</TableHead>
              <TableHead>Holat</TableHead>
              <TableHead>Oxirgi faollik</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-mono text-xs">{user.id}</TableCell>
                <TableCell>{user.username ? `@${user.username}` : "—"}</TableCell>
                <TableCell>{[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}</TableCell>
                <TableCell>
                  {user.is_blocked ? (
                    <Badge variant="destructive">Bloklangan</Badge>
                  ) : (
                    <Badge variant="success">Faol</Badge>
                  )}
                </TableCell>
                <TableCell>{formatDate(user.last_seen_at)}</TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="ghost" size="icon" title="Premium berish" onClick={() => openGrant(user)}>
                    <Star className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => toggleBlock(user)}>
                    {user.is_blocked ? <CheckCircle className="h-4 w-4" /> : <Ban className="h-4 w-4" />}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Foydalanuvchilar topilmadi
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && <PaginationBar page={data.page} size={data.size} total={data.total} onPageChange={setPage} />}
      </div>

      <Dialog open={!!grantTarget} onClose={() => setGrantTarget(null)} title="Premium berish">
        <form onSubmit={onGrant} className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Foydalanuvchi: <span className="font-medium text-foreground">{grantTarget?.id}</span>
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="plan">Tarif</Label>
            <Select
              id="plan"
              value={selectedPlan ?? ""}
              onChange={(e) => setSelectedPlan(Number(e.target.value))}
              required
            >
              <option value="" disabled>
                Tanlang
              </option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name} ({plan.days} kun, {plan.price} so&apos;m)
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" className="w-full" disabled={granting || !selectedPlan}>
            {granting ? "Berilmoqda..." : "Berish"}
          </Button>
        </form>
      </Dialog>
    </div>
  );
}
