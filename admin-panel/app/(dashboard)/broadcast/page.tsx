"use client";

import { useCallback, useEffect, useState } from "react";
import { Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { Broadcast, Page } from "@/lib/types";

const PAGE_SIZE = 20;

const STATUS_VARIANT: Record<string, "secondary" | "success" | "destructive" | "default"> = {
  pending: "secondary",
  running: "default",
  done: "success",
  cancelled: "destructive",
};

export default function BroadcastPage() {
  const [data, setData] = useState<Page<Broadcast> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Page<Broadcast>>("/api/broadcasts", { params: { page, size: PAGE_SIZE } })
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [page]);

  useEffect(() => {
    load();
    // Per the TZ: poll every 3s so a running broadcast's progress updates live.
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, [load]);

  async function onCancel(broadcast: Broadcast) {
    if (!confirm("Broadcast'ni to'xtatmoqchimisiz?")) return;
    await apiFetch(`/api/broadcasts/${broadcast.id}/cancel`, { method: "POST" });
    load();
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Broadcast tarixi</h1>
        <p className="text-sm text-muted-foreground">
          Yangi broadcast faqat bot orqali yuboriladi — bu yerda faqat tarix va to&apos;xtatish tugmasi mavjud.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Maqsad</TableHead>
              <TableHead>Holat</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Boshlangan</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((broadcast) => (
              <TableRow key={broadcast.id}>
                <TableCell>{broadcast.id}</TableCell>
                <TableCell className="capitalize">{broadcast.target}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[broadcast.status] ?? "secondary"}>{broadcast.status}</Badge>
                </TableCell>
                <TableCell>
                  {broadcast.sent}/{broadcast.total} · xato: {broadcast.failed} · blok: {broadcast.blocked}
                </TableCell>
                <TableCell>{formatDate(broadcast.started_at)}</TableCell>
                <TableCell className="text-right">
                  {broadcast.status === "running" && (
                    <Button variant="ghost" size="icon" onClick={() => onCancel(broadcast)}>
                      <Square className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Broadcast tarixi bo&apos;sh
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        {data && <PaginationBar page={data.page} size={data.size} total={data.total} onPageChange={setPage} />}
      </div>
    </div>
  );
}
