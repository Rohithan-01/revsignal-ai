from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.risk_engine import analyze_deal

REQUIRED_FIELDS = {
    "deal_id",
    "account_name",
    "deal_value",
    "stage",
    "status",
}

FIELD_ALIASES = {
    "deal_id": ["deal_id", "dealid", "opportunity_id", "id", "deal", "deal id"],
    "account_name": ["account_name", "account", "account_name", "company", "customer_name", "customer"],
    "deal_value": ["deal_value", "amount", "value", "revenue", "opportunity_value"],
    "stage": ["stage", "sales_stage", "deal_stage", "pipeline_stage"],
    "created_date": ["created_date", "created_at", "created", "date_created"],
    "expected_close_date": ["expected_close_date", "close_date", "expected_close", "close_date_expected"],
    "last_activity_date": ["last_activity_date", "last_activity", "last_touch", "last_contact_date"],
    "activity_count": ["activity_count", "activities", "total_activity_count"],
    "meeting_count": ["meeting_count", "meetings", "meeting_total"],
    "email_count": ["email_count", "emails", "email_total"],
    "stakeholder_count": ["stakeholder_count", "stakeholders", "decision_makers"],
    "status": ["status", "deal_status", "opportunity_status"],
}


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace(" ", "_")


def _coerce_numeric(value: Any) -> float | None:
    if value is None or str(value).strip() in {"", "nan", "NaN"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> datetime | None:
    if value is None or str(value).strip() in {"", "nan", "NaN"}:
        return None
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None


def normalize_record(raw_record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for raw_key, raw_value in raw_record.items():
            normalized_key = _normalize_key(raw_key)
            if normalized_key in {alias.lower() for alias in aliases}:
                normalized[canonical] = raw_value
                break

    if "status" not in normalized or not str(normalized.get("status") or "").strip():
        normalized["status"] = "open"

    if "deal_id" not in normalized or not str(normalized.get("deal_id") or "").strip():
        raise ValueError("The CSV is missing a valid deal_id column or value.")

    if "account_name" not in normalized or not str(normalized.get("account_name") or "").strip():
        raise ValueError("The CSV is missing a valid account_name column or value.")

    if "deal_value" not in normalized:
        normalized["deal_value"] = 0
    if "stage" not in normalized or not str(normalized.get("stage") or "").strip():
        normalized["stage"] = "Unknown"

    normalized["deal_value"] = _coerce_numeric(normalized.get("deal_value")) or 0
    normalized["created_date"] = _coerce_date(normalized.get("created_date"))
    normalized["expected_close_date"] = _coerce_date(normalized.get("expected_close_date"))
    normalized["last_activity_date"] = _coerce_date(normalized.get("last_activity_date"))
    normalized["activity_count"] = _coerce_numeric(normalized.get("activity_count"))
    normalized["meeting_count"] = _coerce_numeric(normalized.get("meeting_count"))
    normalized["email_count"] = _coerce_numeric(normalized.get("email_count"))
    normalized["stakeholder_count"] = _coerce_numeric(normalized.get("stakeholder_count"))

    if normalized["activity_count"] is not None:
        normalized["activity_count"] = int(normalized["activity_count"])
    if normalized["meeting_count"] is not None:
        normalized["meeting_count"] = int(normalized["meeting_count"])
    if normalized["email_count"] is not None:
        normalized["email_count"] = int(normalized["email_count"])
    if normalized["stakeholder_count"] is not None:
        normalized["stakeholder_count"] = int(normalized["stakeholder_count"])

    return normalized


def import_csv_records(file_obj: Any) -> list[dict[str, Any]]:
    uploaded = file_obj.read()
    if not uploaded:
        raise ValueError("The uploaded CSV file is empty.")

    csv_path = Path("/tmp/revsignal_upload.csv")
    csv_path.write_bytes(uploaded)

    try:
        frame = pd.read_csv(csv_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unable to parse the file as CSV: {exc}") from exc

    if frame.empty:
        raise ValueError("The uploaded CSV file does not contain any rows.")

    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        record = normalize_record(row.to_dict())
        rows.append(record)

    if not rows:
        raise ValueError("No records were loaded from the uploaded CSV file.")

    missing_fields = sorted(REQUIRED_FIELDS - set().union(*(row.keys() for row in rows)))
    if missing_fields:
        raise ValueError(
            "The uploaded CSV is missing required fields for the RevSignal schema. "
            f"Missing: {', '.join(missing_fields)}"
        )

    return [analyze_deal(row) for row in rows]


def synthetic_sample_rows() -> list[dict[str, Any]]:
    csv_path = Path(__file__).resolve().parent.parent / "data" / "sample_crm.csv"
    frame = pd.read_csv(csv_path)
    return [normalize_record(row.to_dict()) for _, row in frame.iterrows()]
