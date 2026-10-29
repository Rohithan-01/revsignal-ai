"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  Check,
  CircleHelp,
  Clock3,
  Mail,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Target,
  Users,
} from "lucide-react";
import { useRevenueData } from "@/components/data-provider";
import { RiskBadge, StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, LoadingState } from "@/components/ui/page-states";
import { api, ApiConnectionError } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/formatters";
import type { Deal } from "@/lib/types";

function daysSince(value: string | null): number | null {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  if (Number.isNaN(parsed)) return null;
  return Math.floor((Date.now() - parsed) / 86_400_000);
}

export default function DealDetailPage() {
  const params = useParams<{ dealId: string }>();
  const dealId = decodeURIComponent(params.dealId);
  const { deals, source, loading: dataLoading, refresh, replaceDeal } = useRevenueData();
  const [remoteDeal, setRemoteDeal] = useState<Deal | null>(null);
  const [loadingRemote, setLoadingRemote] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const localDeal = deals.find((deal) => deal.deal_id === dealId);
  const deal = remoteDeal || localDeal;

  useEffect(() => {
    if (source !== "live" || localDeal || !dealId) return;
    let active = true;
    setLoadingRemote(true);
    api.deal(dealId)
      .then((result) => { if (active) setRemoteDeal(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load this deal.");
      })
      .finally(() => { if (active) setLoadingRemote(false); });
    return () => { active = false; };
  }, [source, localDeal, dealId]);

  async function refreshAnalysis() {
    if (source !== "live" || !deal) return;
    setAnalyzing(true);
    setActionMessage("");
    setError(null);
    try {
      const updated = await api.analyze(deal.deal_id);
      replaceDeal(updated);
      setRemoteDeal(updated);
      setActionMessage("Risk assessment updated from the latest deal data.");
    } catch (reason) {
      setError(reason instanceof ApiConnectionError ? reason.message : reason instanceof Error ? reason.message : "Unable to refresh risk analysis.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (dataLoading || loadingRemote) return <LoadingState label="Loading deal intelligence" />;
  if (!deal) {
    return <><Link className="back-link" href="/deals"><ArrowLeft size={15} /> Back to deals</Link><ErrorState message={error || "This deal was not found in the current dataset."} onRetry={() => { setError(null); void refresh(); }} /></>;
  }

  const activityAge = daysSince(deal.last_activity_date);
  const closeAge = deal.expected_close_date ? daysSince(deal.expected_close_date) : null;
  const evidence = deal.risk_reasons || [];
  const missing: string[] = [];
  if (!deal.last_activity_date) missing.push("Last activity date");
  if (deal.expected_close_date == null) missing.push("Expected close date");
  if (deal.stakeholder_count == null) missing.push("Stakeholder count");
  if (deal.activity_count == null) missing.push("Activity count");
  return (
    <>
      <Link className="back-link" href="/deals"><ArrowLeft size={15} /> Back to deals</Link>
      <div className="detail-heading">
        <div className="detail-account-avatar">{deal.account_name.slice(0, 1)}</div>
        <div className="detail-title-copy"><div className="eyebrow">DEAL INTELLIGENCE <span className="detail-breadcrumb-slash">/</span> {deal.deal_id}</div><h1>{deal.account_name}</h1><p>{deal.deal_id} <span className="detail-dot">·</span> {deal.stage} <span className="detail-dot">·</span> {formatCurrency(deal.deal_value)}</p></div>
        <div className="detail-heading-actions"><RiskBadge level={deal.risk_level} /><button className="button button-secondary" onClick={() => void refreshAnalysis()} disabled={source !== "live" || analyzing} title={source !== "live" ? "Analysis refresh requires the live backend." : "Re-run the rule-based deal analysis"}><RefreshCw size={14} className={analyzing ? "spin" : ""} />{analyzing ? "Analyzing…" : "Refresh analysis"}</button></div>
      </div>

      {error && <ErrorState message={error} onRetry={() => void refreshAnalysis()} />}
      {actionMessage && <div className="success-message" role="status"><Check size={15} />{actionMessage}</div>}

      <div className="detail-metrics-grid">
        <article className="detail-metric panel"><span>Deal value</span><strong>{formatCurrency(deal.deal_value)}</strong><small><Target size={13} /> Current opportunity</small></article>
        <article className="detail-metric panel"><span>Expected close</span><strong className="detail-metric-date">{formatDate(deal.expected_close_date)}</strong><small><CalendarClock size={13} /> {closeAge !== null && closeAge > 0 ? `${closeAge} days overdue` : closeAge !== null && closeAge >= -14 ? "Closing within 14 days" : "Target close date"}</small></article>
        <article className="detail-metric panel"><span>Last recorded activity</span><strong className="detail-metric-date">{formatDate(deal.last_activity_date)}</strong><small><Clock3 size={13} /> {activityAge === null ? "No activity date provided" : `${Math.max(activityAge, 0)} days ago`}</small></article>
        <article className="detail-metric panel"><span>Deal status</span><strong><StatusBadge status={deal.status} /></strong><small><Users size={13} /> {deal.stakeholder_count == null ? "Stakeholder count not available" : `${deal.stakeholder_count} stakeholders recorded`}</small></article>
      </div>

      <div className="detail-content-grid">
        <div className="detail-main-column">
          <section className="panel assessment-panel">
            <div className="panel-heading">
              <div><div className="title-with-indicator"><ShieldCheck size={17} className="section-title-icon" /><h2>Risk assessment</h2></div><p>Explainable signals used to evaluate this opportunity.</p></div>
              <span className="assessment-method"><span /> Rule-based</span>
            </div>
            <div className="risk-score-layout">
              <div className={`risk-score-ring ring-${deal.risk_level.toLowerCase()}`}><span><strong>{deal.risk_score}</strong><small>out of 100</small></span></div>
              <div className="risk-score-description"><div><RiskBadge level={deal.risk_level} /><span className="risk-score-caption">Risk classification</span></div><h3>{deal.risk_level === "HIGH" ? "This deal needs prompt attention." : deal.risk_level === "MEDIUM" ? "Keep this opportunity on your radar." : "This deal is showing healthy signals."}</h3><p>Score is determined by transparent rules applied to the fields in your CRM record. It is not produced by a trained machine-learning model.</p></div>
            </div>
            <div className="evidence-block"><h3><AlertTriangle size={15} /> Contributing evidence <span>{evidence.length} signals</span></h3>{evidence.length ? <ul className="evidence-list">{evidence.map((reason, index) => <li key={`${index}-${reason}`}><span className="evidence-bullet" />{reason}</li>)}</ul> : <div className="inline-empty">No risk factors were recorded for this deal.</div>}</div>
          </section>

          <section className="panel factors-panel">
            <div className="panel-heading"><div><h2>Deal signals</h2><p>Available activity and stakeholder information.</p></div></div>
            <div className="factor-grid">
              <div className="factor-item"><Clock3 size={16} /><span>Days since last activity</span><strong>{activityAge === null ? "Not available" : `${Math.max(activityAge, 0)} days`}</strong></div>
              <div className="factor-item"><CalendarClock size={16} /><span>Expected close timing</span><strong>{closeAge === null ? "Not available" : closeAge > 0 ? `${closeAge} days overdue` : closeAge >= -14 ? "Within 14 days" : "Upcoming"}</strong></div>
              <div className="factor-item"><MessageSquareText size={16} /><span>Recorded activity count</span><strong>{deal.activity_count == null ? "Not available" : deal.activity_count}</strong></div>
              <div className="factor-item"><Users size={16} /><span>Stakeholders</span><strong>{deal.stakeholder_count == null ? "Not available" : deal.stakeholder_count}</strong></div>
              <div className="factor-item"><Mail size={16} /><span>Email / meeting records</span><strong>{deal.email_count == null && deal.meeting_count == null ? "Not available" : `${deal.email_count ?? "—"} emails · ${deal.meeting_count ?? "—"} meetings`}</strong></div>
            </div>
            {missing.length > 0 && <div className="missing-info"><CircleHelp size={15} /><span><strong>Missing data:</strong> {missing.join(", ")}. Missing fields are not treated as confirmed negative events.</span></div>}
          </section>
          <section className="panel timeline-panel">
            <div className="panel-heading"><div><h2>Activity timeline</h2><p>Recorded customer interactions for this opportunity.</p></div></div>
            <div className="timeline-empty"><div className="timeline-empty-icon"><Clock3 size={17} /></div><div><strong>No activity timeline available</strong><span>This CRM import includes activity totals only, not individual email, call, or meeting records.</span></div></div>
          </section>
        </div>

        <aside className="detail-aside">
          <section className="panel recommendation-panel">
            <div className="recommendation-title"><div className="recommendation-spark"><RefreshCw size={16} /></div><div><span>NEXT BEST ACTION</span><h2>Recommended next step</h2></div></div>
            <div className="recommendation-copy">{deal.recommended_action || "No recommendation is available for this deal."}</div>
            <div className="recommendation-why"><strong>Why this action?</strong>{evidence.length ? <p>{evidence[0]}</p> : <p>Use the available CRM signals to confirm the next customer milestone.</p>}</div>
            {evidence.length > 1 && <div className="recommendation-support"><strong>Also consider</strong><p>{evidence.slice(1, 3).join(" ")}</p></div>}
            <div className="informational-note"><CircleHelp size={14} /><span>Informational recommendation only. RevSignal does not send messages or execute actions.</span></div>
            <button className="button button-secondary recommendation-refresh" disabled={source !== "live" || analyzing} onClick={() => void refreshAnalysis()}><RefreshCw size={14} className={analyzing ? "spin" : ""} /> Refresh analysis <ArrowRight size={14} /></button>
          </section>
          <section className="panel deal-properties">
            <div className="panel-heading"><div><h2>Deal properties</h2><p>Fields imported from the CRM.</p></div></div>
            <dl><div><dt>Account</dt><dd>{deal.account_name}</dd></div><div><dt>Deal ID</dt><dd>{deal.deal_id}</dd></div><div><dt>Sales stage</dt><dd>{deal.stage || "Not available"}</dd></div><div><dt>Created</dt><dd>{formatDate(deal.created_date)}</dd></div><div><dt>Close date</dt><dd>{formatDate(deal.expected_close_date)}</dd></div><div><dt>Owner</dt><dd>Not provided in this CRM data</dd></div></dl>
          </section>
          <Link className="aside-deals-link" href="/deals">View all deals <ArrowRight size={14} /></Link>
        </aside>
      </div>
    </>
  );
}
