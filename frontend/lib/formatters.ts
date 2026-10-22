import type { RiskLevel } from "@/lib/types";

const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const compactCurrencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});

const dateFormatter = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatCurrency(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? currencyFormatter.format(value)
    : "Not available";
}

export function formatCompactCurrency(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? compactCurrencyFormatter.format(value)
    : "Not available";
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : dateFormatter.format(date);
}

export function riskFromScore(score: number): RiskLevel {
  if (score >= 70) return "HIGH";
  if (score >= 35) return "MEDIUM";
  return "LOW";
}

export function isOpenStatus(status: string): boolean {
  return [
    "open",
    "active",
    "pipeline",
    "qualified",
    "proposal",
    "negotiation",
    "discovery",
    "in_progress",
    "in-progress",
  ].includes(status.trim().toLowerCase());
}
