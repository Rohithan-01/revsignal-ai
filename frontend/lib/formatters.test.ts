import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  isOpenStatus,
  riskFromScore,
} from "@/lib/formatters";

describe("currency and date formatting", () => {
  it("formats full values in Indian rupees", () => {
    assert.equal(formatCurrency(1_200_000), "₹12,00,000");
    assert.equal(formatCurrency(null), "Not available");
  });

  it("formats compact currency values", () => {
    assert.match(formatCompactCurrency(1_200_000), /12/);
    assert.equal(formatCompactCurrency(Number.NaN), "Not available");
  });

  it("formats valid dates and handles missing or invalid dates", () => {
    assert.match(formatDate("2026-01-05"), /2026/);
    assert.equal(formatDate(null), "Not available");
    assert.equal(formatDate("not-a-date"), "Not available");
  });
});

describe("deal classifications", () => {
  for (const [score, level] of [
    [0, "LOW"],
    [34, "LOW"],
    [35, "MEDIUM"],
    [69, "MEDIUM"],
    [70, "HIGH"],
    [100, "HIGH"],
  ] as const) {
    it(`maps a score of ${score} to ${level} risk`, () => {
      assert.equal(riskFromScore(score), level);
    });
  }

  it("recognizes open pipeline statuses", () => {
    assert.equal(isOpenStatus("Open"), true);
    assert.equal(isOpenStatus("in-progress"), true);
    assert.equal(isOpenStatus("closed_lost"), false);
  });
});
