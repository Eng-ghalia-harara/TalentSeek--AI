from __future__ import annotations

import re
import calendar
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo


_MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"),
        start=1,
    )
}
_MONTH_PATTERN = "|".join(_MONTHS)
_RANGE_RE = re.compile(
    rf"(?:(?P<sm>{_MONTH_PATTERN})\s+)?(?P<sy>19\d{{2}}|20\d{{2}})\s*"
    rf"(?:-|\u2013|\u2014|to)\s*(?:(?P<em>{_MONTH_PATTERN})\s+)?"
    rf"(?P<ey>19\d{{2}}|20\d{{2}}|present|current|now)",
    re.IGNORECASE,
)


def _today() -> date:
    try:
        return datetime.now(ZoneInfo("Asia/Hebron")).date()
    except Exception:
        return date.today()


def _month_bounds(year: int, month: int | None) -> tuple[date, date]:
    if month is not None:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return date(year, 1, 1), date(year, 12, 31)


def _years_between(start: date, end: date) -> float:
    return max(0.0, (end - start).days / 365.2425)


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    merged: list[list[date]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    return [(start, end) for start, end in merged]


def add_experience_estimates(candidates: list[dict[str, Any]], today: date | None = None) -> str:
    """Add approximate date-derived work experience to retrieved candidate evidence."""
    reference_date = today or _today()
    for candidate in candidates:
        text = "\n".join(
            str(item.get("content", ""))
            for item in candidate.get("evidence", [])
            if str(item.get("section", "")).strip().lower() == "work experience"
        )
        matches = list(_RANGE_RE.finditer(text))
        starts_early: list[tuple[date, date]] = []
        starts_late: list[tuple[date, date]] = []
        found: list[str] = []

        for match in matches:
            start_year = int(match.group("sy"))
            start_month = _MONTHS.get((match.group("sm") or "").lower())
            if match.group("ey").lower() in {"present", "current", "now"}:
                end_early = end_late = reference_date
            else:
                end_year = int(match.group("ey"))
                end_month = _MONTHS.get((match.group("em") or "").lower())
                end_early, end_late = _month_bounds(end_year, end_month)

            start_early, start_late = _month_bounds(start_year, start_month)
            starts_early.append((start_early, end_late))
            starts_late.append((start_late, end_early))
            found.append(match.group(0))

        if not matches:
            candidate["experience_estimate"] = None
            continue

        # Merge overlapping jobs so simultaneous roles are not counted twice.
        earliest_intervals = _merge_intervals(starts_early)
        latest_intervals = _merge_intervals(starts_late)
        low = sum(_years_between(start, end) for start, end in latest_intervals)
        high = sum(_years_between(start, end) for start, end in earliest_intervals)
        candidate["experience_estimate"] = {
            "approx_years_range": [round(low, 1), round(high, 1)],
            "date_ranges_found": sorted(set(found)),
            "as_of": reference_date.isoformat(),
            "note": "Approximate: CV date ranges may omit months; overlapping roles are not double-counted.",
        }
    return reference_date.isoformat()
