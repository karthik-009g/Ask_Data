import re
from datetime import datetime, timedelta
from numbers import Number
from typing import Any


_IDENTIFIER_HINTS = (
    "id",
    "_id",
    "uuid",
    "guid",
    "connection_id",
    "employee_id",
    "user_id",
)


def _coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Number):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    # Treat mixed alpha-numeric values as labels, not measures (e.g., student names/codes).
    if re.search(r"[A-Za-z]", text):
        return None

    # Normalize common human formats like "1,234", "85%", "$1200".
    normalized = text.replace(",", "")
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    normalized = re.sub(r"^[^0-9\-\.]+", "", normalized)
    normalized = re.sub(r"[^0-9\-\.]+$", "", normalized)
    if not normalized:
        return None

    try:
        return float(normalized)
    except Exception:
        return None


def _looks_like_identifier(column_name: str, values: list[Any], row_count: int) -> bool:
    lowered = str(column_name or "").strip().lower()
    if not lowered:
        return True

    if lowered in _IDENTIFIER_HINTS:
        return True
    if lowered.endswith("_id") or lowered.startswith("id_"):
        return True

    non_null = [value for value in values if value is not None and value != ""]
    if not non_null:
        return False

    unique_ratio = len({str(value) for value in non_null}) / max(1, len(non_null))
    if unique_ratio >= 0.9 and len(non_null) >= max(10, int(row_count * 0.5)):
        return True
    return False


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for parser in (
        datetime.fromisoformat,
        lambda v: datetime.strptime(v, "%Y-%m-%d"),
        lambda v: datetime.strptime(v, "%Y/%m/%d"),
        lambda v: datetime.strptime(v, "%d-%m-%Y"),
    ):
        try:
            return parser(text)
        except Exception:
            continue
    return None


def extract_tables_from_sql(sql_text: str) -> list[str]:
    sql = str(sql_text or "")
    if not sql.strip():
        return []
    pattern = re.compile(r"\b(?:from|join)\s+([\w\.\"`]+)", re.IGNORECASE)
    found = []
    for match in pattern.findall(sql):
        table_name = str(match).strip().strip('"').strip("`")
        if table_name and table_name not in found:
            found.append(table_name)
    return found


def compute_business_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "row_count": 0,
            "numeric_columns": {},
            "business_numeric_columns": {},
            "null_counts": {},
            "suppressed_numeric_columns": [],
        }

    keys = list(rows[0].keys())
    row_count = len(rows)
    null_counts = {key: 0 for key in keys}
    numeric_data: dict[str, list[float]] = {key: [] for key in keys}
    column_values: dict[str, list[Any]] = {key: [] for key in keys}

    for row in rows:
        for key in keys:
            value = row.get(key)
            column_values[key].append(value)
            if value is None or value == "":
                null_counts[key] += 1
                continue
            numeric_value = _coerce_numeric(value)
            if numeric_value is not None:
                numeric_data[key].append(numeric_value)

    numeric_columns: dict[str, dict[str, Any]] = {}
    business_numeric_columns: dict[str, dict[str, Any]] = {}
    suppressed_numeric_columns: list[str] = []

    for key, values in numeric_data.items():
        if not values:
            continue
        total = sum(values)
        stats = {
            "count": len(values),
            "sum": round(total, 4),
            "avg": round(total / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
        numeric_columns[key] = stats
        if _looks_like_identifier(key, column_values[key], row_count):
            suppressed_numeric_columns.append(key)
            continue
        business_numeric_columns[key] = stats

    return {
        "row_count": row_count,
        "numeric_columns": numeric_columns,
        "business_numeric_columns": business_numeric_columns,
        "null_counts": null_counts,
        "suppressed_numeric_columns": suppressed_numeric_columns,
    }


def build_trend_snapshot(rows: list[dict[str, Any]], analytics: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {"has_time_series": False, "time_column": None, "weekly_changes": []}

    keys = list(rows[0].keys())
    datetime_candidates: list[tuple[str, int]] = []
    parsed_cache: dict[str, list[datetime | None]] = {}

    for key in keys:
        parsed = [_parse_datetime(row.get(key)) for row in rows]
        parsed_cache[key] = parsed
        parseable = sum(1 for item in parsed if item is not None)
        if parseable >= max(3, int(len(rows) * 0.6)):
            datetime_candidates.append((key, parseable))

    if not datetime_candidates:
        return {"has_time_series": False, "time_column": None, "weekly_changes": []}

    datetime_candidates.sort(key=lambda item: item[1], reverse=True)
    time_column = datetime_candidates[0][0]
    parsed_dates = parsed_cache[time_column]
    business_metrics = list((analytics.get("business_numeric_columns") or {}).keys())
    if not business_metrics:
        return {"has_time_series": True, "time_column": time_column, "weekly_changes": []}

    day_metric_totals: dict[datetime.date, dict[str, float]] = {}
    latest_date: datetime | None = None
    for index, row in enumerate(rows):
        dt_value = parsed_dates[index]
        if dt_value is None:
            continue
        latest_date = dt_value if latest_date is None or dt_value > latest_date else latest_date
        day_key = dt_value.date()
        if day_key not in day_metric_totals:
            day_metric_totals[day_key] = {metric: 0.0 for metric in business_metrics}
        for metric in business_metrics:
            metric_value = row.get(metric)
            if isinstance(metric_value, (int, float)):
                day_metric_totals[day_key][metric] += float(metric_value)

    if not latest_date:
        return {"has_time_series": True, "time_column": time_column, "weekly_changes": []}

    last_day = latest_date.date()
    this_week_start = last_day - timedelta(days=6)
    prev_week_start = this_week_start - timedelta(days=7)
    prev_week_end = this_week_start - timedelta(days=1)

    weekly_changes: list[dict[str, Any]] = []
    for metric in business_metrics[:5]:
        this_week_total = 0.0
        prev_week_total = 0.0
        for day_key, totals in day_metric_totals.items():
            if this_week_start <= day_key <= last_day:
                this_week_total += float(totals.get(metric, 0.0))
            elif prev_week_start <= day_key <= prev_week_end:
                prev_week_total += float(totals.get(metric, 0.0))

        if this_week_total == 0 and prev_week_total == 0:
            continue

        if prev_week_total == 0:
            pct_change = None
            direction = "new"
        else:
            pct_change = round(((this_week_total - prev_week_total) / max(1e-9, prev_week_total)) * 100, 2)
            direction = "up" if pct_change > 0 else "down" if pct_change < 0 else "flat"

        weekly_changes.append(
            {
                "metric": metric,
                "this_week": round(this_week_total, 4),
                "previous_week": round(prev_week_total, 4),
                "pct_change": pct_change,
                "direction": direction,
            }
        )

    return {
        "has_time_series": True,
        "time_column": time_column,
        "weekly_changes": weekly_changes,
    }


def build_proactive_alerts(analytics: dict[str, Any], trend_snapshot: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    row_count = int(analytics.get("row_count", 0) or 0)
    null_counts = analytics.get("null_counts", {}) or {}
    business_numeric = analytics.get("business_numeric_columns", {}) or {}

    for column_name, null_count in list(null_counts.items())[:6]:
        if row_count == 0:
            break
        ratio = float(null_count) / float(max(1, row_count))
        if ratio >= 0.25:
            alerts.append(f"{column_name} has {round(ratio * 100)}% missing values; validate data quality before making decisions.")

    for metric, stats in list(business_numeric.items())[:5]:
        avg_value = float(stats.get("avg", 0) or 0)
        max_value = float(stats.get("max", 0) or 0)
        if avg_value > 0 and max_value >= avg_value * 3:
            alerts.append(f"{metric} shows spike behavior (max is over 3x average).")

    for weekly in trend_snapshot.get("weekly_changes", [])[:5]:
        pct = weekly.get("pct_change")
        if pct is None:
            alerts.append(f"{weekly.get('metric')} appears in the latest week with no previous-week baseline.")
            continue
        if abs(float(pct)) >= 15:
            direction = "increase" if float(pct) > 0 else "decrease"
            alerts.append(f"{weekly.get('metric')} shows a {direction} of {abs(float(pct))}% week-over-week.")

    if not alerts and row_count:
        alerts.append("No high-risk anomalies detected in this result set.")

    return alerts[:8]


def build_human_business_brief(
    prompt: str,
    generated_queries: list[dict[str, Any]],
    analytics: dict[str, Any],
    proactive_alerts: list[str],
    trend_snapshot: dict[str, Any],
    tables_in_scope: list[str],
    tables_used: list[str],
) -> str:
    row_count = int(analytics.get("row_count", 0) or 0)
    business_numeric = analytics.get("business_numeric_columns", {}) or {}
    top_metrics = list(business_numeric.items())[:3]

    lines = [
        "What I did:",
        f"- Interpreted your request: {prompt}",
        f"- Queried {len(generated_queries)} source(s) and returned {row_count} row(s)",
    ]

    if tables_used:
        lines.append(f"- Tables used: {', '.join(tables_used[:8])}")
    elif tables_in_scope:
        lines.append(f"- Tables considered by planner: {', '.join(tables_in_scope[:8])}")

    lines.append("What changed and what matters:")
    if top_metrics:
        for metric, stats in top_metrics:
            lines.append(
                f"- {metric}: avg {stats.get('avg')}, range {stats.get('min')} to {stats.get('max')}"
            )
    else:
        lines.append("- Numeric business metrics were limited in this result set.")

    weekly_changes = trend_snapshot.get("weekly_changes", [])
    if weekly_changes:
        for weekly in weekly_changes[:3]:
            pct = weekly.get("pct_change")
            if pct is None:
                lines.append(f"- {weekly.get('metric')}: present in the latest week with no prior-week baseline.")
            else:
                lines.append(f"- {weekly.get('metric')}: {pct}% week-over-week.")
    elif trend_snapshot.get("has_time_series"):
        lines.append("- Time field was detected, but weekly trend contrast was not strong enough to compute.")
    else:
        lines.append("- No explicit time field was returned, so 1-week trend comparison could not be calculated.")

    lines.append("Business guidance:")
    if proactive_alerts:
        lines.append(f"- Priority signal: {proactive_alerts[0]}")
    lines.append("- Next best step: run a focused follow-up query by product/region/team for root-cause breakdown.")

    return "\n".join(lines)
