export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface Deal {
  id: number | null;
  deal_id: string;
  account_name: string;
  deal_value: number;
  stage: string;
  status: string;
  created_date: string | null;
  expected_close_date: string | null;
  last_activity_date: string | null;
  activity_count: number | null;
  meeting_count: number | null;
  email_count: number | null;
  stakeholder_count: number | null;
  risk_score: number;
  risk_level: RiskLevel;
  risk_reasons: string[];
  recommended_action: string;
}

export interface Metrics {
  total_open_pipeline_value: number;
  revenue_high_risk: number;
  high_risk_deals: number;
  deals_needing_attention: number;
  deal_distribution_by_risk: Record<RiskLevel, number>;
  pipeline_value_by_stage: Record<string, number>;
  top_deals: Deal[];
}

export interface UploadResponse {
  success: boolean;
  message: string;
  records_imported: number;
}

export type DataSource = "live" | "demo";

export interface RevenueData {
  deals: Deal[];
  metrics: Metrics;
  source: DataSource;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  replaceDeal: (deal: Deal) => void;
}
