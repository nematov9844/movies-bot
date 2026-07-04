"use client";

import { Button } from "@/components/ui/button";

interface PaginationBarProps {
  page: number;
  size: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function PaginationBar({ page, size, total, onPageChange }: PaginationBarProps) {
  const totalPages = Math.max(1, Math.ceil(total / size));

  return (
    <div className="flex items-center justify-between border-t px-3 py-2 text-sm text-muted-foreground">
      <span>
        Jami: <span className="font-medium text-foreground">{total}</span>
      </span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Oldingi
        </Button>
        <span>
          {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Keyingi
        </Button>
      </div>
    </div>
  );
}
