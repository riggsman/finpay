import { useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 10;

/**
 * Client-side pagination for Back Office lists/tables.
 * Shows controls only when there are more than `pageSize` records.
 */
export function usePagination(items, pageSize = PAGE_SIZE) {
  const list = Array.isArray(items) ? items : [];
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [list.length, pageSize]);

  const total = list.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const safePage = Math.min(page, totalPages);

  const pageItems = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return list.slice(start, start + pageSize);
  }, [list, safePage, pageSize]);

  return {
    page: safePage,
    setPage,
    pageSize,
    total,
    totalPages,
    pageItems,
    needsPagination: total > pageSize,
  };
}

export default function Pagination({ page, totalPages, total, pageSize, onChange }) {
  if (total <= pageSize) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="pagination-bar">
      <span className="muted small">
        Showing {start}–{end} of {total}
      </span>
      <div className="pagination-controls">
        <button
          type="button"
          className="btn-ghost"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Previous
        </button>
        <span className="pagination-page">
          Page {page} / {totalPages}
        </span>
        <button
          type="button"
          className="btn-ghost"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
