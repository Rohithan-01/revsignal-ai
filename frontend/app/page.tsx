"use client";

import Link from "next/link";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CircleHelp,
  DollarSign,
  Flame,
  Layers3,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { motion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useRevenueData } from "@/components/data-provider";
import { PriorityDealsTable } from "@/components/deals/deals-table";
import { CopilotPanel } from "@/components/dashboard/copilot-panel";
import { MetricCard } from "@/components/dashboard/metric-card";
import { ErrorState, LoadingState } from "@/components/ui/page-states";
import { formatCompactCurrency, formatCurrency, isOpenStatus } from "@/lib/formatters";

const riskColors: Record<string, string> = { LOW: "#27a77a", MEDIUM: "#e5a02e", HIGH: "#e05b5b" };

export default function OverviewPage() {
  const { deals, metrics, loading, error, refresh, source } = useRevenueData();
  const openDeals = deals.filter((deal) => isOpenStatus(deal.status));
  const attentionCount = openDeals.filter((deal) => deal.risk_level !== "LOW").length;
  const distribution = ["LOW", "MEDIUM", "HIGH"].map((risk) => ({
    name: risk,
    value: metrics.deal_distribution_by_risk?.[risk as keyof typeof metrics.deal_distribution_by_risk] || 0,
  }));
  const stageData = Object.entries(metrics.pipeline_value_by_stage || {}).map(([stage, value]) => ({
    stage,
    value,
    deal_count: openDeals.filter((deal) => deal.stage === stage).length,
  }));
  const highRiskByStage = Object.entries(
    openDeals.filter((deal) => deal.risk_level === "HIGH").reduce<Record<string, number>>((totals, deal) => {
      totals[deal.stage] = (totals[deal.stage] || 0) + deal.deal_value;
      return totals;
    }, {}),
  ).map(([stage, value]) => ({ stage, value })).sort((a, b) => b.value - a.value).slice(0, 4);
  const openValue = metrics.total_open_pipeline_value;
  const highRiskValue = metrics.revenue_high_risk;
  const highRiskCount = metrics.high_risk_deals;
  const attentionTotal = source === "live" ? metrics.deals_needing_attention : attentionCount;

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-dot" /> REVENUE INTELLIGENCE</div>
          <h1>Revenue overview</h1>
          <p>Find at-risk deals, understand why, and prioritize your next move.</p>
        </div>
        <div className="heading-actions">
          <span className="period-label"><span className="period-dot" /> Current pipeline</span>
          <Link className="button button-primary" href="/deals">Explore deals <ArrowRight size={15} /></Link>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => void refresh()} />}
      {loading ? <LoadingState /> : (
        <>
          <section className="kpi-grid" aria-label="Pipeline summary">
            <MetricCard label="Open pipeline" value={openValue} kind="currency" icon={<DollarSign size={17} />} iconStyle="icon-indigo" help="Total deal value for all open opportunities in the current pipeline." detail={<><span className="kpi-foot-neutral"><Layers3 size={13} /> {openDeals.length} active deals</span><span className="kpi-period">Current pipeline</span></>} index={0} />
            <MetricCard label="Revenue at risk" value={highRiskValue} kind="currency" icon={<Flame size={17} />} iconStyle="icon-rose" help="Value associated with open high-risk deals. This is not a prediction of revenue loss." detail={<><span className="kpi-foot-negative"><ArrowUpRight size={13} /> {openValue ? `${((highRiskValue / openValue) * 100).toFixed(1)}%` : "0%"} of pipeline</span><span className="kpi-period">High risk only</span></>} index={1} />
            <MetricCard label="High-risk deals" value={highRiskCount} kind="count" icon={<ShieldCheck size={17} />} iconStyle="icon-amber" help="Open deals with a rule-based risk score of 70 or higher." detail={<><span className="kpi-foot-negative"><ArrowDownRight size={13} /> Prioritize today</span><span className="kpi-period">Score ≥ 70</span></>} index={2} />
            <MetricCard label="Needs attention" value={attentionTotal} kind="count" icon={<Sparkles size={17} />} iconStyle="icon-blue" help="Unique open deals classified as medium or high risk by the current scoring rules." detail={<><span className="kpi-foot-neutral">Medium + high risk</span><span className="kpi-period">Needs follow-up</span></>} index={3} />
          </section>

          <motion.section className="dashboard-layout" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38 }}>
            <div className="dashboard-main-stack">
              <article className="panel chart-panel">
              <div className="panel-heading">
                <div><h2>Pipeline by stage</h2><p>Open pipeline value across sales stages</p></div>
                <span className="chart-unit">VALUE</span>
              </div>
              {stageData.length ? (
                <div className="chart-area">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={stageData} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke="#eef1f6" />
                      <XAxis dataKey="stage" axisLine={false} tickLine={false} tick={{ fill: "#858da0", fontSize: 11 }} dy={9} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fill: "#858da0", fontSize: 11 }} tickFormatter={(value: number) => formatCompactCurrency(value)} width={78} />
                      <Tooltip
                        cursor={{ fill: "#f6f8fc" }}
                        content={({ active, payload }) => {
                          const entry = payload?.[0]?.payload as (typeof stageData)[number] | undefined;
                          return active && entry ? <div className="chart-tooltip"><strong>{entry.stage}</strong><span>{entry.deal_count} {entry.deal_count === 1 ? "deal" : "deals"}</span><b>{formatCurrency(entry.value)}</b></div> : null;
                        }}
                      />
                      <Bar dataKey="value" fill="#5d6ee8" radius={[5, 5, 0, 0]} maxBarSize={42} isAnimationActive animationDuration={650} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <div className="chart-empty">Import CRM data to see pipeline by stage.</div>}
              </article>
              <section className="panel priority-panel">
                <div className="panel-heading priority-heading">
                  <div><div className="title-with-indicator"><span className="attention-indicator" /><h2>Deals requiring attention</h2></div><p>Start with the opportunities carrying the most risk.</p></div>
                  <Link className="text-link" href="/deals">View all deals <ArrowRight size={14} /></Link>
                </div>
                {openDeals.length ? <PriorityDealsTable deals={openDeals} /> : <div className="empty-state"><strong>No pipeline data yet</strong><span>Import a CRM CSV to get explainable deal risk and next steps.</span><Link href="/import" className="button button-primary">Import data</Link></div>}
              </section>
            </div>
            <aside className="dashboard-side-stack">
              <article className="panel chart-panel risk-chart-panel">
              <div className="panel-heading">
                <div><h2>Deal risk distribution</h2><p>Open deals by rule-based risk level</p></div>
                <span className="chart-unit">DEALS</span>
              </div>
              <div className="risk-chart-content">
                {distribution.some((item) => item.value > 0) ? (
                  <>
                    <div className="donut-wrap">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie data={distribution} dataKey="value" nameKey="name" innerRadius={58} outerRadius={78} paddingAngle={4} stroke="none" isAnimationActive animationDuration={700}>
                            {distribution.map((item) => <Cell key={item.name} fill={riskColors[item.name]} />)}
                          </Pie>
                          <Tooltip formatter={(value, name) => [`${value} deals`, name]} contentStyle={{ borderRadius: 10, border: "1px solid #e8ebf1", fontSize: 12 }} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="donut-center"><strong>{openDeals.length}</strong><span>open deals</span></div>
                    </div>
                    <div className="risk-legend">
                      {distribution.map((item) => <div className="legend-row" key={item.name}><span className="legend-name"><i style={{ background: riskColors[item.name] }} />{item.name.toLowerCase()} risk</span><strong>{item.value}<small>{openDeals.length ? ` · ${Math.round(item.value / openDeals.length * 100)}%` : ""}</small></strong></div>)}
                    </div>
                  </>
                ) : <div className="chart-empty">Import CRM data to see risk distribution.</div>}
              </div>
              </article>
              <article className="panel revenue-risk-panel">
                <div className="panel-heading"><div><h2>Revenue at risk</h2><p>Value in open high-risk deals</p></div><span className="risk-stat-icon"><Flame size={15} /></span></div>
                <div className="revenue-risk-value">{formatCompactCurrency(highRiskValue)}</div>
                <div className="revenue-risk-caption">{highRiskCount} {highRiskCount === 1 ? "high-risk deal" : "high-risk deals"} <span>·</span> {openValue ? `${((highRiskValue / openValue) * 100).toFixed(1)}% of pipeline` : "0% of pipeline"}</div>
                {highRiskByStage.length ? <div className="risk-stage-list">{highRiskByStage.map(({ stage, value }) => <div className="risk-stage-row" key={stage}><span>{stage}</span><div className="risk-stage-track"><i style={{ width: `${highRiskValue ? Math.max(4, value / highRiskValue * 100) : 0}%` }} /></div><strong>{formatCompactCurrency(value)}</strong></div>)}</div> : <div className="risk-stage-empty">No open high-risk deals.</div>}
                <span className="risk-disclaimer"><CircleHelp size={12} /> Associated value, not forecast loss.</span>
              </article>
              <CopilotPanel />
            </aside>
          </motion.section>
          <div className="dashboard-footnote"><ShieldCheck size={14} /> Risk scores are generated by transparent, rule-based analysis — not a trained ML model.</div>
        </>
      )}
    </>
  );
}
