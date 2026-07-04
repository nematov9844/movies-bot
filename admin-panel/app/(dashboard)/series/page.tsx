"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Pencil, Trash2, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import type { Page, Series } from "@/lib/types";

const PAGE_SIZE = 20;

interface SeriesFormState {
  title: string;
  description: string;
  poster_file_id: string;
}

const EMPTY_FORM: SeriesFormState = { title: "", description: "", poster_file_id: "" };

export default function SeriesPage() {
  const [data, setData] = useState<Page<Series> | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Series | null>(null);
  const [form, setForm] = useState<SeriesFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    apiFetch<Page<Series>>("/api/series", { params: { page, size: PAGE_SIZE, q } })
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [page, q]);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(series: Series) {
    setEditing(series);
    setForm({
      title: series.title,
      description: series.description ?? "",
      poster_file_id: series.poster_file_id ?? "",
    });
    setDialogOpen(true);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = {
        title: form.title,
        description: form.description || null,
        poster_file_id: form.poster_file_id || null,
      };
      if (editing) {
        await apiFetch(`/api/series/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await apiFetch("/api/series", { method: "POST", body: JSON.stringify(body) });
      }
      setDialogOpen(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(series: Series) {
    if (!confirm(`"${series.title}" serialini butunlay o'chirmoqchimisiz? (Fasllar ham o'chadi)`)) return;
    await apiFetch(`/api/series/${series.id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Seriallar</h1>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" /> Yangi serial
        </Button>
      </div>

      <Input
        placeholder="Nomi bo'yicha qidirish..."
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
              <TableHead>Nomi</TableHead>
              <TableHead>Tavsif</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((series) => (
              <TableRow key={series.id}>
                <TableCell>
                  <Link href={`/series/${series.id}`} className="flex items-center gap-1 font-medium hover:underline">
                    {series.title} <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{series.description ?? "—"}</TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="ghost" size="icon" onClick={() => openEdit(series)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => onDelete(series)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Seriallar topilmadi
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && <PaginationBar page={data.page} size={data.size} total={data.total} onPageChange={setPage} />}
      </div>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? "Serialni tahrirlash" : "Yangi serial"}
      >
        <form onSubmit={onSave} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="title">Nomi</Label>
            <Input id="title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="description">Tavsif</Label>
            <Textarea
              id="description"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="poster_file_id">Poster (Telegram photo file_id, ixtiyoriy)</Label>
            <Input
              id="poster_file_id"
              value={form.poster_file_id}
              onChange={(e) => setForm({ ...form, poster_file_id: e.target.value })}
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
