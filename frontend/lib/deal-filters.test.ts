import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { demoDeals } from "@/lib/demo-data";
import { filterDeals } from "@/lib/deal-filters";

describe("deal explorer filters", () => {
  it("searches deal IDs and account names without case sensitivity", () => {
    assert.deepEqual(filterDeals(demoDeals, { search: "BLUEPEAK" }).map((deal) => deal.deal_id), ["D-1007"]);
    assert.deepEqual(filterDeals(demoDeals, { search: "d-1002" }).map((deal) => deal.account_name), ["Harbor Retail"]);
  });

  it("combines risk, stage, and status filters", () => {
    const matching = filterDeals(demoDeals, { risk: "HIGH", stage: "Negotiation", status: "OPEN" });
    assert.deepEqual(matching.map((deal) => deal.deal_id), ["D-1002"]);
  });

  it("sorts by value and expected close date", () => {
    const byValue = filterDeals(demoDeals, { sort: "deal_value" });
    assert.equal(byValue[0].deal_id, "D-1007");
    const byClose = filterDeals(demoDeals, { sort: "expected_close_date" });
    assert.equal(byClose[0].deal_id, "D-1006");
  });
});
