"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import type { Deal } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/formatters";
import { RiskBadge, StatusBadge } from "@/components/ui/status-badge";

export function PriorityDealsTable({ deals }: { deals: Deal[] }) {
  const priority = [...deals]
    .filter((deal) => deal.risk_level !== "LOW")
    .sort((a, b) => {
      const riskOrder = { HIGH: 2, MEDIUM: 1, LOW: 0 };
      return riskOrder[b.risk_level] - riskOrder[a.risk_level] || b.risk_score - a.risk_score;
    })
    .slice(0, 6);

  if (priority.length === 0) {
    return (
      <div className="empty-state compact-empty">
        <div className="empty-icon success-icon"><ChevronRight size={19} /></div>
        <strong>No deals need attention</strong>
        <span>Open opportunities currently have low risk signals.</span>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table priority-table">
        <thead><tr>
          <th>Deal / account</th><th>Deal value</th><th>Stage</th><th>Risk score</th><th>Last activity</th><th>Recommended next action</th><th aria-label="Open detail" />
        </tr></thead>
        <tbody>
          {priority.map((deal) => (
            <tr key={deal.deal_id}>
              <td><Link className="deal-name-link" href={`/deals/${encodeURIComponent(deal.deal_id)}`}><span className="deal-initial">{deal.account_name.slice(0, 1)}</span><span><strong>{deal.account_name}</strong><small>{deal.deal_id}</small></span></Link></td>
              <td className="table-value">{formatCurrency(deal.deal_value)}</td>
              <td>{deal.stage || "Not available"}</td>
              <td><span className="risk-score-cell"><RiskBadge level={deal.risk_level} /><span>{deal.risk_score}</span></span></td>
              <td className="muted-cell">{formatDate(deal.last_activity_date)}</td>
              <td className="action-cell">{deal.recommended_action || "No recommendation available"}</td>
              <td><Link className="row-open-link" href={`/deals/${encodeURIComponent(deal.deal_id)}`} aria-label={`View ${deal.account_name}`}><ArrowUpRight size={15} /></Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DealsDataTable({ deals }: { deals: Deal[] }) {
  if (!deals.length) {
    return (
      <div className="empty-state">
        <div className="empty-icon"><ArrowUpRight size={19} /></div>
        <strong>No deals match these filters</strong>
        <span>Try adjusting your search or filters, or import a CRM CSV.</span>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table explorer-table">
        <thead><tr>
          <th>Deal ID</th><th>Account</th><th>Deal value</th><th>Stage</th><th>Status</th><th>Risk score</th><th>Last activity</th><th>Expected close</th><th />
        </tr></thead>
        <tbody>
          {deals.map((deal) => (
            <tr key={deal.deal_id}>
              <td><Link className="id-link" href={`/deals/${encodeURIComponent(deal.deal_id)}`}>{deal.deal_id}</Link></td>
              <td><Link className="account-link" href={`/deals/${encodeURIComponent(deal.deal_id)}`}>{deal.account_name}</Link></td>
              <td className="table-value">{formatCurrency(deal.deal_value)}</td>
              <td>{deal.stage || "Not available"}</td>
              <td><StatusBadge status={deal.status || "unknown"} /></td>
              <td><span className="risk-score-cell"><RiskBadge level={deal.risk_level} /><span>{deal.risk_score}</span></span></td>
              <td className="muted-cell">{formatDate(deal.last_activity_date)}</td>
              <td className="muted-cell">{formatDate(deal.expected_close_date)}</td>
              <td><Link className="row-open-link" href={`/deals/${encodeURIComponent(deal.deal_id)}`} aria-label={`View ${deal.deal_id}`}><ChevronRight size={16} /></Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
