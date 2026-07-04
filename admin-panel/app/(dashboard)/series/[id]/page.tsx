"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Plus, Trash2, ChevronDown, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, ApiError } from "@/lib/api";
import type { Movie, Page, Season, SeriesWithSeasons } from "@/lib/types";

export default function SeriesDetailPage() {
  const params = useParams<{ id: string }>();
  const seriesId = Number(params.id);

  const [series, setSeries] = useState<SeriesWithSeasons | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [seasonNumber, setSeasonNumber] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedSeasonId, setExpandedSeasonId] = useState<number | null>(null);

  const load = useCallback(() => {
    apiFetch<SeriesWithSeasons>(`/api/series/${seriesId}`)
      .then(setSeries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [seriesId]);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreateSeason(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/api/series/${seriesId}/seasons`, {
        method: "POST",
        body: JSON.stringify({ number: Number(seasonNumber) }),
      });
      setDialogOpen(false);
      setSeasonNumber("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSaving(false);
    }
  }

  async function onDeleteSeason(season: Season) {
    if (!confirm(`${season.number}-faslni o'chirmoqchimisiz? (Qismlar oddiy kino sifatida qoladi)`)) return;
    await apiFetch(`/api/series/seasons/${season.id}`, { method: "DELETE" });
    load();
  }

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!series) return <p className="text-muted-foreground">Yuklanmoqda...</p>;

  return (
    <div className="space-y-4">
      <Link href="/series" className="flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="h-3.5 w-3.5" /> Seriallar
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{series.title}</h1>
          {series.description && <p className="text-sm text-muted-foreground">{series.description}</p>}
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Fasl qo&apos;shish
        </Button>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead />
              <TableHead>Fasl</TableHead>
              <TableHead>Qismlar soni</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {series.seasons.map((season) => (
              <SeasonRow
                key={season.id}
                season={season}
                expanded={expandedSeasonId === season.id}
                onToggle={() => setExpandedSeasonId(expandedSeasonId === season.id ? null : season.id)}
                onDelete={() => onDeleteSeason(season)}
              />
            ))}
            {series.seasons.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Fasllar mavjud emas. Qismlarni botdagi &quot;📺 Seriallar&quot; orqali forward qilib qo&apos;shing.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="Yangi fasl">
        <form onSubmit={onCreateSeason} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="number">Fasl raqami</Label>
            <Input
              id="number"
              type="number"
              min={1}
              value={seasonNumber}
              onChange={(e) => setSeasonNumber(e.target.value)}
              required
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Qismlarni (video fayllarni) shu faslga qo&apos;shish uchun botda &quot;📺 Seriallar&quot; bo&apos;limidan foydalaning —
            videolarni birma-bir forward qilasiz.
          </p>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? "Saqlanmoqda..." : "Saqlash"}
          </Button>
        </form>
      </Dialog>
    </div>
  );
}

function SeasonRow({
  season,
  expanded,
  onToggle,
  onDelete,
}: {
  season: Season;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <>
      <TableRow>
        <TableCell className="w-8">
          <button onClick={onToggle} className="rounded-md p-1 hover:bg-accent" aria-label="Qismlarni ko'rsatish">
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </TableCell>
        <TableCell className="font-medium">{season.number}-fasl</TableCell>
        <TableCell>{season.episode_count}</TableCell>
        <TableCell className="text-right">
          <Button variant="ghost" size="icon" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={4} className="bg-muted/30 p-0">
            <EpisodeList seasonId={season.id} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

const EPISODES_PAGE_SIZE = 50;

function EpisodeList({ seasonId }: { seasonId: number }) {
  const [data, setData] = useState<Page<Movie> | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    apiFetch<Page<Movie>>(`/api/series/seasons/${seasonId}/episodes`, {
      params: { page, size: EPISODES_PAGE_SIZE },
    }).then(setData);
  }, [seasonId, page]);

  if (!data) return <p className="p-3 text-sm text-muted-foreground">Yuklanmoqda...</p>;
  if (data.items.length === 0) return <p className="p-3 text-sm text-muted-foreground">Qismlar mavjud emas.</p>;

  return (
    <div className="space-y-2 p-3">
      <ul className="divide-y">
        {data.items.map((episode) => (
          <li key={episode.id} className="flex items-center justify-between py-1.5 text-sm">
            <span>{episode.title}</span>
            <span className="flex items-center gap-2">
              <code className="text-xs text-muted-foreground">{episode.code}</code>
              {episode.is_premium && <Badge variant="default">Premium</Badge>}
            </span>
          </li>
        ))}
      </ul>
      {data.total > EPISODES_PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Jami: {data.total}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Oldingi
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page * EPISODES_PAGE_SIZE >= data.total}
              onClick={() => setPage(page + 1)}
            >
              Keyingi
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
