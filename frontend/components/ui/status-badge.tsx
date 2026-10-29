import type { RiskLevel } from "@/lib/types";

export function RiskBadge({ level }: { level: RiskLevel }) {
  return <span className={`badge badge-${level.toLowerCase()}`}>{level}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/[_-]/g, " ");
  return <span className={`status-badge status-${status.toLowerCase().replace(/[^a-z]+/g, "-")}`}>{normalized}</span>;
}
