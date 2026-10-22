import assert from "node:assert/strict";
import { it } from "node:test";
import { demoDeals, demoMetrics } from "@/lib/demo-data";

it("calculates the demo dashboard metrics from open sample deals", () => {
  const metrics = demoMetrics(demoDeals);
  assert.equal(metrics.total_open_pipeline_value, 1_883_000);
  assert.equal(metrics.revenue_high_risk, 288_000);
  assert.equal(metrics.high_risk_deals, 2);
  assert.equal(metrics.deals_needing_attention, 4);
  assert.deepEqual(metrics.deal_distribution_by_risk, { LOW: 3, MEDIUM: 2, HIGH: 2 });
});
