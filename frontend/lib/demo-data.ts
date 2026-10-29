import type { Deal, Metrics, RiskLevel } from "@/lib/types";
import { isOpenStatus } from "@/lib/formatters";

function demoDeal(
  deal_id: string,
  account_name: string,
  deal_value: number,
  stage: string,
  expected_close_date: string,
  last_activity_date: string,
  activity_count: number,
  meeting_count: number,
  email_count: number,
  stakeholder_count: number,
  risk_score: number,
  risk_reasons: string[],
  recommended_action: string,
  status = "open",
): Deal {
  const risk_level: RiskLevel =
    risk_score >= 70 ? "HIGH" : risk_score >= 35 ? "MEDIUM" : "LOW";
  return {
    id: null,
    deal_id,
    account_name,
    deal_value,
    stage,
    status,
    created_date: null,
    expected_close_date,
    last_activity_date,
    activity_count,
    meeting_count,
    email_count,
    stakeholder_count,
    risk_score,
    risk_level,
    risk_reasons,
    recommended_action,
  };
}

export const demoDeals: Deal[] = [
  demoDeal("D-1002", "Harbor Retail", 68_000, "Negotiation", "2026-10-12", "2026-09-15", 2, 0, 2, 1, 86, ["The expected close date is overdue.", "Stakeholder coverage appears limited.", "No meetings have been recorded."], "Review the close date, confirm customer commitment, and escalate the account if the decision is still pending."),
  demoDeal("D-1003", "Apex Manufacturing", 220_000, "Discovery", "2026-11-15", "2026-09-28", 1, 0, 1, 1, 72, ["The opportunity has very limited recent activity.", "No meetings have been recorded.", "Stakeholder coverage appears limited."], "Identify missing decision-makers and validate the buying committee before the next conversation."),
  demoDeal("D-1004", "Meridian Health", 310_000, "Proposal", "2026-10-20", "2026-09-27", 4, 2, 6, 4, 58, ["Customer activity has slowed.", "The expected close date is approaching."], "Stay engaged with the customer, confirm the next milestone, and monitor the deal closely."),
  demoDeal("D-1008", "Greenline Logistics", 175_000, "Qualified", "2026-10-18", "2026-10-16", 6, 2, 7, 3, 40, ["The expected close date is approaching."], "Stay engaged with the customer, confirm the next milestone, and monitor the deal closely."),
  demoDeal("D-1001", "Northwind Labs", 150_000, "Proposal", "2026-10-25", "2026-10-05", 5, 1, 8, 3, 27, ["The expected close date is approaching."], "Maintain the current outreach cadence and validate the next customer milestone."),
  demoDeal("D-1005", "Velora Systems", 420_000, "Qualified", "2026-11-01", "2026-10-11", 7, 3, 10, 5, 27, ["The expected close date is approaching."], "Maintain the current outreach cadence and validate the next customer milestone."),
  demoDeal("D-1007", "BluePeak Financial", 540_000, "Proposal", "2026-10-28", "2026-10-13", 9, 4, 12, 5, 27, ["The expected close date is approaching."], "Maintain the current outreach cadence and validate the next customer milestone."),
  demoDeal("D-1006", "Summit Legal", 96_000, "Negotiation", "2026-09-30", "2026-08-22", 2, 1, 2, 2, 65, ["The expected close date is overdue.", "Customer activity has slowed."], "Review the close date, confirm customer commitment, and escalate if the decision is pending.", "lost"),
];

export function demoMetrics(deals: Deal[]): Metrics {
  const openDeals = deals.filter((deal) => isOpenStatus(deal.status));
  const deal_distribution_by_risk: Metrics["deal_distribution_by_risk"] = {
    LOW: 0,
    MEDIUM: 0,
    HIGH: 0,
  };
  const pipeline_value_by_stage: Record<string, number> = {};

  for (const deal of openDeals) {
    deal_distribution_by_risk[deal.risk_level] += 1;
    pipeline_value_by_stage[deal.stage] =
      (pipeline_value_by_stage[deal.stage] || 0) + deal.deal_value;
  }

  const highRisk = openDeals.filter((deal) => deal.risk_level === "HIGH");
  const needsAttention = openDeals.filter((deal) => deal.risk_level !== "LOW");
  return {
    total_open_pipeline_value: openDeals.reduce((sum, deal) => sum + deal.deal_value, 0),
    revenue_high_risk: highRisk.reduce((sum, deal) => sum + deal.deal_value, 0),
    high_risk_deals: highRisk.length,
    deals_needing_attention: needsAttention.length,
    deal_distribution_by_risk,
    pipeline_value_by_stage,
    top_deals: [...openDeals].sort((a, b) => b.risk_score - a.risk_score).slice(0, 10),
  };
}
