"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Power } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, ApiError } from "@/lib/api";
import type { Channel } from "@/lib/types";

interface ChannelFormState {
  channel_id: string;
  title: string;
  username: string;
  invite_link: string;
  priority: string;
  join_limit: string;
}

const EMPTY_FORM: ChannelFormState = {
  channel_id: "",
  title: "",
  username: "",
  invite_link: "",
  priority: "0",
  join_limit: "",
};

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Channel | null>(null);
  const [form, setForm] = useState<ChannelFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    apiFetch<Channel[]>("/api/channels")
      .then(setChannels)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(channel: Channel) {
    setEditing(channel);
    setForm({
      channel_id: String(channel.channel_id),
      title: channel.title,
      username: channel.username ?? "",
      invite_link: channel.invite_link ?? "",
      priority: String(channel.priority),
      join_limit: channel.join_limit ? String(channel.join_limit) : "",
    });
    setDialogOpen(true);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await apiFetch(`/api/channels/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            priority: Number(form.priority),
            join_limit: form.join_limit ? Number(form.join_limit) : null,
          }),
        });
      } else {
        await apiFetch("/api/channels", {
          method: "POST",
          body: JSON.stringify({
            channel_id: Number(form.channel_id),
            title: form.title,
            username: form.username || null,
            invite_link: form.invite_link || null,
            priority: Number(form.priority || 0),
            join_limit: form.join_limit ? Number(form.join_limit) : null,
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

  async function onToggle(channel: Channel) {
    await apiFetch(`/api/channels/${channel.id}/toggle`, { method: "POST" });
    load();
  }

  async function onDelete(channel: Channel) {
    if (!confirm(`"${channel.title}" kanalini butunlay o'chirmoqchimisiz?`)) return;
    await apiFetch(`/api/channels/${channel.id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Kanallar (Force Subscribe)</h1>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" /> Kanal qo&apos;shish
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nomi</TableHead>
              <TableHead>Havola</TableHead>
              <TableHead>Ustuvorlik</TableHead>
              <TableHead>Obunachilar</TableHead>
              <TableHead>Holat</TableHead>
              <TableHead className="text-right">Amallar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {channels.map((channel) => (
              <TableRow key={channel.id}>
                <TableCell>{channel.title}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {channel.username ? `@${channel.username}` : channel.invite_link ?? "—"}
                </TableCell>
                <TableCell>{channel.priority}</TableCell>
                <TableCell>
                  {channel.current_joins}
                  {channel.join_limit ? ` / ${channel.join_limit}` : ""}
                </TableCell>
                <TableCell>
                  {channel.is_active ? <Badge variant="success">Yoqilgan</Badge> : <Badge variant="destructive">O&apos;chirilgan</Badge>}
                </TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="ghost" size="icon" onClick={() => onToggle(channel)}>
                    <Power className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => openEdit(channel)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => onDelete(channel)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {channels.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Kanallar mavjud emas
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title={editing ? "Kanalni tahrirlash" : "Kanal qo'shish"}>
        <form onSubmit={onSave} className="space-y-4">
          {!editing && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="channel_id">Telegram kanal ID (-100...)</Label>
                <Input
                  id="channel_id"
                  value={form.channel_id}
                  onChange={(e) => setForm({ ...form, channel_id: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="title">Nomi</Label>
                <Input id="title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="username">Username (ixtiyoriy)</Label>
                <Input id="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite_link">Invite link (private kanal uchun)</Label>
                <Input
                  id="invite_link"
                  value={form.invite_link}
                  onChange={(e) => setForm({ ...form, invite_link: e.target.value })}
                />
              </div>
            </>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="priority">Ustuvorlik</Label>
            <Input
              id="priority"
              type="number"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="join_limit">Obunachilar chegarasi (bo&apos;sh — cheksiz)</Label>
            <Input
              id="join_limit"
              type="number"
              value={form.join_limit}
              onChange={(e) => setForm({ ...form, join_limit: e.target.value })}
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
