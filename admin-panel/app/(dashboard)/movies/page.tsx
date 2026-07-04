"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import type { Movie, Page } from "@/lib/types";

const PAGE_SIZE = 20;

interface MovieFormState {
  code: string;
  title: string;
  description: string;
  file_id: string;
  poster_file_id: string;
  is_premium: boolean;
}

const EMPTY_FORM: MovieFormState = {
  code: "",
  title: "",
  description: "",
  file_id: "",
  poster_file_id: "",
  is_premium: false,
};

export default function MoviesPage() {
  const [data, setData] = useState<Page<Movie> | null>(null);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Movie | null>(null);
  const [form, setForm] = useState<MovieFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    apiFetch<Page<Movie>>("/api/movies", { params: { page, size: PAGE_SIZE, q } })
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

  function openEdit(movie: Movie) {
    setEditing(movie);
    setForm({
      code: movie.code,
      title: movie.title,
      description: movie.description ?? "",
      file_id: movie.file_id,
      poster_file_id: movie.poster_file_id ?? "",
      is_premium: movie.is_premium,
    });
    setDialogOpen(true);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await apiFetch(`/api/movies/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            code: form.code,
            title: form.title,
            description: form.description || null,
            poster_file_id: form.poster_file_id || null,
            is_premium: form.is_premium,
          }),
        });
      } else {
        await apiFetch("/api/movies", {
          method: "POST",
          body: JSON.stringify({
            code: form.code,
            title: form.title,
            description: form.description || null,
            file_id: form.file_id,
            poster_file_id: form.poster_file_id || null,
            is_premium: form.is_premium,
          }),
        });
      }
      setDialogOpen(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(movie: Movie) {
    if (!confirm(`"${movie.title}" kinosini o'chirmoqchimisiz?`)) return;
    await apiFetch(`/api/movies/${movie.id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Kinolar</h1>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" /> Kino qo&apos;shish
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
              <TableHead>Kod</TableHead>
              <TableHead>Nomi</TableHead>
              <TableHead>Premium</TableHead>
              <TableHead>Holat</TableHead>
              <TableHead>Ko&apos;rishlar</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((movie) => (
              <TableRow key={movie.id}>
                <TableCell className="font-mono text-xs">{movie.code}</TableCell>
                <TableCell>{movie.title}</TableCell>
                <TableCell>
                  {movie.is_premium ? <Badge variant="default">Premium</Badge> : <Badge variant="secondary">Oddiy</Badge>}
                </TableCell>
                <TableCell>
                  {movie.is_active ? <Badge variant="success">Faol</Badge> : <Badge variant="destructive">Nofaol</Badge>}
                </TableCell>
                <TableCell>{movie.view_count}</TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="ghost" size="icon" onClick={() => openEdit(movie)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => onDelete(movie)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Kinolar topilmadi
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && <PaginationBar page={data.page} size={data.size} total={data.total} onPageChange={setPage} />}
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title={editing ? "Kinoni tahrirlash" : "Kino qo'shish"}>
        <form onSubmit={onSave} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="code">Kod</Label>
            <Input id="code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
          </div>
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
          {!editing && (
            <div className="space-y-1.5">
              <Label htmlFor="file_id">Telegram file_id</Label>
              <Input
                id="file_id"
                value={form.file_id}
                onChange={(e) => setForm({ ...form, file_id: e.target.value })}
                required
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="poster_file_id">Poster (Telegram photo file_id, ixtiyoriy)</Label>
            <Input
              id="poster_file_id"
              value={form.poster_file_id}
              onChange={(e) => setForm({ ...form, poster_file_id: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="is_premium"
              type="checkbox"
              checked={form.is_premium}
              onChange={(e) => setForm({ ...form, is_premium: e.target.checked })}
              className="h-4 w-4 rounded border-input"
            />
            <Label htmlFor="is_premium">Premium kino</Label>
          </div>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </form>
      </Dialog>
    </div>
  );
}
