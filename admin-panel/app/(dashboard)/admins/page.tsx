"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Admin, AdminRole } from "@/lib/types";

interface AdminFormState {
  user_id: string;
  role: AdminRole;
  password: string;
}

const EMPTY_FORM: AdminFormState = { user_id: "", role: "moderator", password: "" };

export default function AdminsPage() {
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<AdminFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    apiFetch<Admin[]>("/api/admins")
      .then(setAdmins)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/api/admins", {
        method: "POST",
        body: JSON.stringify({ user_id: Number(form.user_id), role: form.role, password: form.password }),
      });
      setDialogOpen(false);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(admin: Admin) {
    if (!confirm(`Admin #${admin.user_id}ni o'chirmoqchimisiz?`)) return;
    try {
      await apiFetch(`/api/admins/${admin.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Adminlar</h1>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Admin qo&apos;shish
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Telegram ID</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Holat</TableHead>
              <TableHead>Qo&apos;shilgan</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {admins.map((admin) => (
              <TableRow key={admin.id}>
                <TableCell className="font-mono text-xs">{admin.user_id}</TableCell>
                <TableCell className="capitalize">{admin.role}</TableCell>
                <TableCell>
                  {admin.is_active ? <Badge variant="success">Faol</Badge> : <Badge variant="destructive">Nofaol</Badge>}
                </TableCell>
                <TableCell>{formatDate(admin.created_at)}</TableCell>
                <TableCell className="text-right">
                  {admin.role !== "owner" && (
                    <Button variant="ghost" size="icon" onClick={() => onDelete(admin)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="Admin qo'shish">
        <form onSubmit={onCreate} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="user_id">Telegram ID</Label>
            <Input
              id="user_id"
              value={form.user_id}
              onChange={(e) => setForm({ ...form, user_id: e.target.value })}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Rol</Label>
            <Select
              id="role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as AdminRole })}
            >
              <option value="moderator">moderator</option>
              <option value="admin">admin</option>
              <option value="owner">owner</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Parol</Label>
            <Input
              id="password"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              minLength={6}
              required
            />
          </div>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saqlanmoqda..." : "Qo'shish"}
          </Button>
        </form>
      </Dialog>
    </div>
  );
}
