"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, ApiError } from "@/lib/api";
import type { Setting } from "@/lib/types";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Setting[]>("/api/settings")
      .then((list) => {
        setSettings(list);
        setDrafts(Object.fromEntries(list.map((s) => [s.key, s.value])));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Xatolik"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onSave(key: string) {
    setSavingKey(key);
    try {
      await apiFetch(`/api/settings/${key}`, {
        method: "PATCH",
        body: JSON.stringify({ value: drafts[key] }),
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xatolik");
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Sozlamalar</h1>
      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {settings.map((setting) => (
          <Card key={setting.key}>
            <CardHeader>
              <CardTitle>{setting.key}</CardTitle>
              {setting.description && <p className="text-xs text-muted-foreground">{setting.description}</p>}
            </CardHeader>
            <CardContent className="space-y-3">
              {setting.type === "bool" ? (
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                  value={drafts[setting.key] ?? setting.value}
                  onChange={(e) => setDrafts({ ...drafts, [setting.key]: e.target.value })}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : setting.value.length > 60 ? (
                <Textarea
                  value={drafts[setting.key] ?? setting.value}
                  onChange={(e) => setDrafts({ ...drafts, [setting.key]: e.target.value })}
                  rows={3}
                />
              ) : (
                <Input
                  value={drafts[setting.key] ?? setting.value}
                  onChange={(e) => setDrafts({ ...drafts, [setting.key]: e.target.value })}
                />
              )}
              <Button
                size="sm"
                onClick={() => onSave(setting.key)}
                disabled={savingKey === setting.key || drafts[setting.key] === setting.value}
              >
                {savingKey === setting.key ? "Saqlanmoqda..." : "Saqlash"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
