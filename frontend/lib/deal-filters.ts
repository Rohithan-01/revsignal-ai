import type { Deal, RiskLevel } from "@/lib/types";

export type DealSortKey = "risk_score" | "deal_value" | "expected_close_date";

export interface DealFilters {
  search?: string;
  risk?: RiskLevel | "";
  stage?: string;
  status?: string;
  sort?: DealSortKey;
}

export function filterDeals(deals: Deal[], filters: DealFilters): Deal[] {
  const query = filters.search?.trim().toLowerCase() || "";
  return deals
    .filter((deal) => !query || deal.deal_id.toLowerCase().includes(query) || deal.account_name.toLowerCase().includes(query))
    .filter((deal) => !filters.risk || deal.risk_level === filters.risk)
    .filter((deal) => !filters.stage || deal.stage === filters.stage)
    .filter((deal) => !filters.status || deal.status.toLowerCase() === filters.status.toLowerCase())
    .sort((a, b) => {
      if (filters.sort === "deal_value") return b.deal_value - a.deal_value;
      if (filters.sort === "expected_close_date") {
        return (a.expected_close_date || "9999").localeCompare(b.expected_close_date || "9999");
      }
      return b.risk_score - a.risk_score;
    });
}
