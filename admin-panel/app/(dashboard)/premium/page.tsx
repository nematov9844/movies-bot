"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Ban } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Page, PremiumPlan, PremiumUserRow } from "@/lib/types";

const PAGE_SIZE = 20;

interface PlanFormState {
  name: string;
  days: string;
  price: string;
}

const EMPTY_PLAN: PlanFormState = { name: "", days: "", price: "" };

export default function PremiumPage() {
  const [plans, setPlans] = useState<PremiumPlan[]>([]);
  const [subs, setSubs] = useState<Page<PremiumUserRow> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PremiumPlan | null>(null);
  const [form, setForm] = useState<PlanFormState>(EMPTY_PLAN);
  const [saving, setSaving] = useState(false);

  const loadPlans = useCallback(() => {
    apiFetch<PremiumPlan[]>("/api/premium/plans")
      .then(setPlans)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, []);

  const loadSubs = useCallback(() => {
    apiFetch<Page<PremiumUserRow>>("/api/premium/subscriptions", { params: { page, size: PAGE_SIZE } })
      .then(setSubs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [page]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);
  useEffect(() => {
    loadSubs();
  }, [loadSubs]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_PLAN);
    setDialogOpen(true);
  }

  function openEdit(plan: PremiumPlan) {
    setEditing(plan);
    setForm({ name: plan.name, days: String(plan.days), price: String(plan.price) });
    setDialogOpen(true);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name: form.name, days: Number(form.days), price: Number(form.price) };
      if (editing) {
        await apiFetch(`/api/premium/plans/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await apiFetch("/api/premium/plans", { method: "POST", body: JSON.stringify(body) });
      }
      setDialogOpen(false);
      loadPlans();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSaving(false);
    }
  }

  async function onDeactivate(plan: PremiumPlan) {
    if (!confirm(`"${plan.name}" tarifini o'chirmoqchimisiz?`)) return;
    await apiFetch(`/api/premium/plans/${plan.id}`, { method: "DELETE" });
    loadPlans();
  }

  return (
    <div className="space-y-8">
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Premium tariflar</h1>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> Tarif qo&apos;shish
          </Button>
        </div>

        {error && <p className="mb-2 text-sm text-destructive">{error}</p>}

        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nomi</TableHead>
                <TableHead>Kunlar</TableHead>
                <TableHead>Narx</TableHead>
                <TableHead>Holat</TableHead>
                <TableHead className="text-right">Amallar</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plans.map((plan) => (
                <TableRow key={plan.id}>
                  <TableCell>{plan.name}</TableCell>
                  <TableCell>{plan.days}</TableCell>
                  <TableCell>{plan.price.toLocaleString()} so&apos;m</TableCell>
                  <TableCell>
                    {plan.is_active ? <Badge variant="success">Faol</Badge> : <Badge variant="destructive">Nofaol</Badge>}
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(plan)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    {plan.is_active && (
                      <Button variant="ghost" size="icon" onClick={() => onDeactivate(plan)}>
                        <Ban className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div>
        <h2 className="mb-4 text-xl font-semibold">Aktiv obunalar</h2>
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Foydalanuvchi</TableHead>
                <TableHead>Tarif</TableHead>
                <TableHead>Boshlangan</TableHead>
                <TableHead>Tugash sanasi</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subs?.items.map((sub) => (
                <TableRow key={sub.id}>
                  <TableCell>{sub.username ? `@${sub.username}` : sub.user_id}</TableCell>
                  <TableCell>{sub.plan_name}</TableCell>
                  <TableCell>{formatDate(sub.starts_at)}</TableCell>
                  <TableCell>{formatDate(sub.expires_at)}</TableCell>
                </TableRow>
              ))}
              {subs?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    Aktiv obunalar yo&apos;q
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {subs && <PaginationBar page={subs.page} size={subs.size} total={subs.total} onPageChange={setPage} />}
        </div>
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title={editing ? "Tarifni tahrirlash" : "Tarif qo'shish"}>
        <form onSubmit={onSave} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="name">Nomi</Label>
            <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="days">Kunlar soni</Label>
            <Input
              id="days"
              type="number"
              min={1}
              value={form.days}
              onChange={(e) => setForm({ ...form, days: e.target.value })}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="price">Narx (so&apos;m)</Label>
            <Input
              id="price"
              type="number"
              min={0}
              value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })}
              required
            />
          </div>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </form>
      </Dialog>
    </div>
  );
}
