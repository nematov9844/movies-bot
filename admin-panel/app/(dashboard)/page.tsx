"use client";

import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import type { DashboardResponse } from "@/lib/types";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<DashboardResponse>("/api/stats")
      .then(setData)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="text-destructive">{error}</p>;
  if (!data) return <p className="text-muted-foreground">Yuklanmoqda...</p>;

  const { summary, daily } = data;

  const cards = [
    { label: "Jami foydalanuvchilar", value: summary.total_users },
    { label: "Bugun yangi userlar", value: summary.new_users_today },
    { label: "Jami kinolar", value: summary.total_movies },
    { label: "Aktiv premium", value: summary.active_premium_count },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.label}>
            <CardHeader>
              <CardTitle>{card.label}</CardTitle>
            </CardHeader>
            <CardContent className="text-2xl font-bold">{formatNumber(card.value)}</CardContent>
          </Card>
        ))}
        <Card>
          <CardHeader>
            <CardTitle>Premium konversiya</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">{summary.premium_conversion_percent}%</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Oxirgi 30 kun</CardTitle>
        </CardHeader>
        <CardContent className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={daily}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="date" fontSize={12} tickMargin={8} />
              <YAxis fontSize={12} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="new_users" name="Yangi userlar" stroke="#2563eb" strokeWidth={2} />
              <Line type="monotone" dataKey="active_users" name="Aktiv userlar" stroke="#16a34a" strokeWidth={2} />
              <Line type="monotone" dataKey="movies_sent" name="Yuborilgan kinolar" stroke="#d97706" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
