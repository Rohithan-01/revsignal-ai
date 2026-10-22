from __future__ import annotations

from datetime import datetime
from io import BytesIO
import math
from typing import Any, Optional

import pandas as pd

from app.risk_engine import analyze_deal

REQUIRED_FIELDS = {"deal_id", "account_name", "deal_value", "stage", "status"}
FIELD_ALIASES = {
    "deal_id": ["deal_id", "dealid", "opportunity_id", "id", "deal"],
    "account_name": ["account_name", "account", "company", "customer_name", "customer"],
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
FIELD_ALIAS_LOOKUP = {
    alias.lower(): canonical
    for canonical, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace(" ", "_")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or bool(pd.isna(value))


def _coerce_numeric(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> Optional[datetime]:
    if _is_blank(value):
        return None
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None


def normalize_record(raw_record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for raw_key, raw_value in raw_record.items():
        canonical = FIELD_ALIAS_LOOKUP.get(_normalize_key(raw_key))
        if canonical is not None:
            normalized[canonical] = raw_value

    if "status" not in normalized or _is_blank(normalized["status"]):
        normalized["status"] = "open"
    if "deal_id" not in normalized or _is_blank(normalized["deal_id"]):
        raise ValueError("The CSV is missing a valid deal_id column or value.")
    if "account_name" not in normalized or _is_blank(normalized["account_name"]):
        raise ValueError("The CSV is missing a valid account_name column or value.")
    if "deal_value" not in normalized:
        normalized["deal_value"] = 0
    if "stage" not in normalized or _is_blank(normalized["stage"]):
        normalized["stage"] = "Unknown"

    if "deal_value" in normalized:
        deal_value = _coerce_numeric(normalized["deal_value"])
        if deal_value is None or not math.isfinite(deal_value) or deal_value < 0:
            raise ValueError("deal_value must be a non-negative number.")
        normalized["deal_value"] = deal_value
    else:
        normalized["deal_value"] = 0
    normalized["created_date"] = _coerce_date(normalized.get("created_date"))
    normalized["expected_close_date"] = _coerce_date(normalized.get("expected_close_date"))
    normalized["last_activity_date"] = _coerce_date(normalized.get("last_activity_date"))

    for key in ("activity_count", "meeting_count", "email_count", "stakeholder_count"):
        value = _coerce_numeric(normalized.get(key))
        normalized[key] = int(value) if value is not None else None

    return normalized


def import_csv_records(file_obj: Any) -> list[dict[str, Any]]:
    uploaded = file_obj.read()
    if not uploaded:
        raise ValueError("The uploaded CSV file is empty.")

    try:
        frame = pd.read_csv(BytesIO(uploaded))
    except Exception as exc:
        raise ValueError(f"Unable to parse the uploaded file as CSV: {exc}") from exc

    if frame.empty:
        raise ValueError("The uploaded CSV file does not contain any rows.")

    present_fields = {
        FIELD_ALIAS_LOOKUP.get(_normalize_key(column))
        for column in frame.columns
    }
    missing_fields = sorted(REQUIRED_FIELDS - present_fields)
    if missing_fields:
        raise ValueError(
            "The uploaded CSV is missing required fields for the RevSignal schema. "
            f"Missing: {', '.join(missing_fields)}"
        )

    rows = []
    seen_deal_ids: set[str] = set()
    for row_number, raw_row in enumerate(frame.to_dict(orient="records"), start=2):
        try:
            row = normalize_record(raw_row)
        except ValueError as exc:
            raise ValueError(f"Invalid CSV row {row_number}: {exc}") from exc
        deal_id = str(row["deal_id"]).strip()
        if deal_id in seen_deal_ids:
            raise ValueError(f"Duplicate deal_id {deal_id!r} on CSV row {row_number}.")
        seen_deal_ids.add(deal_id)
        rows.append(row)
    if not rows:
        raise ValueError("No records were loaded from the uploaded CSV file.")

    return [analyze_deal(row) for row in rows]


def synthetic_sample_rows() -> list[dict[str, Any]]:
    sample_file = Path(__file__).resolve().parent.parent / "data" / "sample_crm.csv"
    frame = pd.read_csv(sample_file)
    return [normalize_record(row) for row in frame.to_dict(orient="records")]
