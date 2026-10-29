"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp, ChevronLeft, ChevronRight, Search, SlidersHorizontal, X } from "lucide-react";
import { useRevenueData } from "@/components/data-provider";
import { DealsDataTable } from "@/components/deals/deals-table";
import { ErrorState, LoadingState } from "@/components/ui/page-states";
import { filterDeals, type DealSortKey } from "@/lib/deal-filters";
import type { RiskLevel } from "@/lib/types";

const PAGE_SIZE = 10;

export default function DealsPage() {
  const { deals, loading, error, refresh } = useRevenueData();
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState<"" | RiskLevel>("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<DealSortKey>("risk_score");
  const [page, setPage] = useState(1);
  const stages = useMemo(() => [...new Set(deals.map((deal) => deal.stage).filter(Boolean))].sort(), [deals]);
  const statuses = useMemo(() => [...new Set(deals.map((deal) => deal.status).filter(Boolean))].sort(), [deals]);

  const filtered = useMemo(
    () => filterDeals(deals, { search, risk, stage, status, sort }),
    [deals, search, risk, stage, status, sort],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageDeals = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const hasFilters = Boolean(search || risk || stage || status);

  function clearFilters() {
    setSearch("");
    setRisk("");
    setStage("");
    setStatus("");
    setPage(1);
  }

  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow"><span className="eyebrow-dot" /> PIPELINE WORKSPACE</div><h1>Deals explorer</h1><p>Search, filter, and inspect every opportunity in your pipeline.</p></div>
        <span className="result-count"><strong>{filtered.length}</strong> {filtered.length === 1 ? "deal" : "deals"}</span>
      </div>
      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {loading ? <LoadingState label="Loading deals" /> : (
        <section className="panel explorer-panel">
          <div className="explorer-toolbar">
            <label className="search-field"><Search size={16} /><input aria-label="Search deals" placeholder="Search by deal ID or account…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />{search && <button className="clear-search" aria-label="Clear search" onClick={() => setSearch("")}><X size={14} /></button>}</label>
            <div className="filter-group">
              <label className="filter-select-label"><SlidersHorizontal size={15} /><span className="sr-only">Risk category</span><select aria-label="Filter by risk" value={risk} onChange={(event) => { setRisk(event.target.value as "" | RiskLevel); setPage(1); }}><option value="">All risk levels</option><option value="HIGH">High risk</option><option value="MEDIUM">Medium risk</option><option value="LOW">Low risk</option></select></label>
              <label className="select-label"><span className="sr-only">Filter by stage</span><select aria-label="Filter by stage" value={stage} onChange={(event) => { setStage(event.target.value); setPage(1); }}><option value="">All stages</option>{stages.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
              <label className="select-label"><span className="sr-only">Filter by deal status</span><select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option>{statuses.map((item) => <option value={item} key={item}>{item.replace(/[_-]/g, " ")}</option>)}</select></label>
              <label className="sort-label"><ArrowDownUp size={14} /><span className="sr-only">Sort deals</span><select aria-label="Sort deals" value={sort} onChange={(event) => setSort(event.target.value as DealSortKey)}><option value="risk_score">Risk score</option><option value="deal_value">Deal value</option><option value="expected_close_date">Expected close</option></select></label>
            </div>
            {hasFilters && <button className="clear-filters" onClick={clearFilters}>Clear filters <X size={13} /></button>}
          </div>
          <DealsDataTable deals={pageDeals} />
          {filtered.length > 0 && <div className="pagination"><span>Showing <strong>{(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)}</strong> of <strong>{filtered.length}</strong> deals</span><div className="pagination-controls"><button aria-label="Previous page" className="pagination-button" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></button><span>Page {currentPage} of {totalPages}</span><button aria-label="Next page" className="pagination-button" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></button></div></div>}
        </section>
      )}
    </>
  );
}
