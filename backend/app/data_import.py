from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
import math
from pathlib import Path
import re
from typing import Any, Optional

import pandas as pd

from .risk_engine import analyze_deal

REQUIRED_FIELDS = {"deal_id", "account_name", "deal_value", "stage", "status"}
FIELD_ALIASES = {
    "deal_id": ["deal_id", "dealid", "opportunity_id", "id", "deal"],
    "account_name": ["account_name", "account", "company", "customer_name", "customer"],
    "deal_value": ["deal_value", "amount", "value", "revenue", "opportunity_value"],
    "probability": ["probability", "close_probability", "win_probability"],
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
DEAL_ID_PATTERN = re.compile(r"D-([1-9][0-9]*)\Z")


def validate_deal_id(value: Any) -> str:
    deal_id = str(value).strip()
    if not DEAL_ID_PATTERN.fullmatch(deal_id):
        raise ValueError("deal_id must use the canonical format D-<positive integer>.")
    return deal_id


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


def _coerce_date(value: Any) -> Optional[date]:
    if _is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError(
        "date values must use YYYY-MM-DD, MM/DD/YYYY, or YYYY/MM/DD format."
    )


def _coerce_count(key: str, value: Any) -> Optional[int]:
    if _is_blank(value):
        return None
    numeric_value = _coerce_numeric(value)
    if numeric_value is None:
        raise ValueError(f"{key} must be a non-negative integer.")
    if (
        not math.isfinite(numeric_value)
        or numeric_value < 0
        or not numeric_value.is_integer()
    ):
        raise ValueError(f"{key} must be a non-negative integer.")
    return int(numeric_value)


def _coerce_probability(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    probability = _coerce_numeric(value)
    if (
        probability is None
        or not math.isfinite(probability)
        or not 0 <= probability <= 100
    ):
        raise ValueError("probability must be a number between 0 and 100.")
    return probability


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
    normalized["deal_id"] = validate_deal_id(normalized["deal_id"])
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
    normalized["probability"] = _coerce_probability(
        normalized.get("probability")
    )
    normalized["probability_is_known"] = normalized["probability"] is not None
    normalized["created_date"] = _coerce_date(normalized.get("created_date"))
    normalized["expected_close_date"] = _coerce_date(normalized.get("expected_close_date"))
    normalized["last_activity_date"] = _coerce_date(normalized.get("last_activity_date"))

    for key in ("activity_count", "meeting_count", "email_count", "stakeholder_count"):
        normalized[key] = _coerce_count(key, normalized.get(key))

    return normalized


def import_csv_records(file_obj: Any) -> list[dict[str, Any]]:
    uploaded = file_obj.read()
    if not uploaded:
        raise ValueError("The uploaded CSV file is empty.")

    try:
        contents = uploaded.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The uploaded CSV file must use UTF-8 encoding.") from exc

    reader = csv.reader(StringIO(contents, newline=""), strict=True)
    try:
        headers = next(reader, None)
        if headers is None:
            raise ValueError("The uploaded CSV file does not contain a header row.")
        present_fields = [
            FIELD_ALIAS_LOOKUP.get(_normalize_key(column))
            for column in headers
        ]
        missing_fields = sorted(REQUIRED_FIELDS - set(present_fields))
        if missing_fields:
            raise ValueError(
                "The uploaded CSV is missing required fields for the RevSignal "
                f"schema. Missing: {', '.join(missing_fields)}"
            )
        known_fields = [field for field in present_fields if field is not None]
        if len(set(known_fields)) != len(known_fields):
            raise ValueError("The uploaded CSV contains duplicate field headers.")

        rows = []
        seen_deal_ids: set[str] = set()
        for values in reader:
            row_number = reader.line_num
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise ValueError(
                    f"Malformed CSV row {row_number}: expected {len(headers)} "
                    f"columns, received {len(values)}."
                )
            try:
                row = normalize_record(dict(zip(headers, values)))
            except ValueError as exc:
                raise ValueError(f"Invalid CSV row {row_number}: {exc}") from exc
            deal_id = str(row["deal_id"]).strip()
            if deal_id in seen_deal_ids:
                raise ValueError(
                    f"Duplicate deal_id {deal_id!r} on CSV row {row_number}."
                )
            seen_deal_ids.add(deal_id)
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(
            f"Malformed CSV near row {reader.line_num}: {exc}"
        ) from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Unable to parse the uploaded file as CSV: {exc}") from exc

    if not rows:
        raise ValueError("The uploaded CSV file does not contain any rows.")

    return [analyze_deal(row) for row in rows]


def synthetic_sample_rows() -> list[dict[str, Any]]:
    sample_file = (
        Path(__file__).resolve().parents[2] / "data" / "sample_crm.csv"
    )
    frame = pd.read_csv(sample_file)
    return [normalize_record(row) for row in frame.to_dict(orient="records")]
