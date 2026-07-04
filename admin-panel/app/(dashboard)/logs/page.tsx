"use client";

import { useCallback, useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaginationBar } from "@/components/pagination-bar";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AuditLog, Page } from "@/lib/types";

const PAGE_SIZE = 30;

export default function LogsPage() {
  const [data, setData] = useState<Page<AuditLog> | null>(null);
  const [page, setPage] = useState(1);
  const [adminId, setAdminId] = useState("");
  const [action, setAction] = useState("");
  const [day, setDay] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Page<AuditLog>>("/api/audit-logs", {
      params: { page, size: PAGE_SIZE, admin_id: adminId || undefined, action: action || undefined, day: day || undefined },
    })
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, [page, adminId, action, day]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Audit loglar</h1>

      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="admin_id">Admin ID</Label>
          <Input
            id="admin_id"
            value={adminId}
            onChange={(e) => {
              setAdminId(e.target.value);
              setPage(1);
            }}
            className="w-32"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="action">Amal</Label>
          <Input
            id="action"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
            className="w-48"
            placeholder="movie_create..."
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="day">Sana</Label>
          <Input
            id="day"
            type="date"
            value={day}
            onChange={(e) => {
              setDay(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Vaqt</TableHead>
              <TableHead>Admin</TableHead>
              <TableHead>Amal</TableHead>
              <TableHead>Obyekt</TableHead>
              <TableHead>IP</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((log) => (
              <TableRow key={log.id}>
                <TableCell>{formatDate(log.created_at)}</TableCell>
                <TableCell>{log.admin_id ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{log.action}</TableCell>
                <TableCell>
                  {log.entity}
                  {log.entity_id ? ` #${log.entity_id}` : ""}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{log.ip ?? "—"}</TableCell>
              </TableRow>
            ))}
            {data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loglar topilmadi
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
