from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable, Literal

from app.models.core import AvailabilityPreference

MatchStatus = Literal["match", "partial", "conflict", "unknown"]
DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")


@dataclass(frozen=True)
class MatchSlot:
    weekday: int
    start_time: str
    end_time: str
    detail: str


@dataclass(frozen=True)
class ScheduleMatchResult:
    status: MatchStatus
    matching_slots: list[MatchSlot]
    partial_slots: list[MatchSlot]
    conflicting_slots: list[MatchSlot]
    summary: str


def _value(item, name: str):
    return item[name] if isinstance(item, dict) else getattr(item, name)


def _minutes(value: str | time) -> int:
    parsed = time.fromisoformat(value) if isinstance(value, str) else value
    return parsed.hour * 60 + parsed.minute


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _preference(window) -> str:
    value = _value(window, "preference")
    return value.value if isinstance(value, AvailabilityPreference) else str(value or "preferred").lower()


def evaluate_schedule_match(
    group_slots: Iterable,
    student_windows: Iterable,
    group_location_id=None,
    preferred_location_id=None,
) -> ScheduleMatchResult:
    slots, windows = list(group_slots), list(student_windows)
    if not windows:
        return ScheduleMatchResult("unknown", [], [], [], "Побажаний час не вказаний. Уточніть графік у сім’ї.")
    if not slots:
        return ScheduleMatchResult("unknown", [], [], [], "Розклад групи ще не вказаний.")

    matching: list[MatchSlot] = []
    partial: list[MatchSlot] = []
    conflicts: list[MatchSlot] = []
    preferred_fits = 0
    for slot in slots:
        weekday = int(_value(slot, "weekday"))
        start = _minutes(_value(slot, "start_time"))
        end = start + int(_value(slot, "duration_minutes"))
        same_day = [window for window in windows if int(_value(window, "weekday")) == weekday]
        acceptable = [window for window in same_day if _preference(window) != "avoid"]
        avoided = [window for window in same_day if _preference(window) == "avoid"]
        label = f"{DAY_NAMES[weekday]} {_clock(start)}–{_clock(end)}"

        full = [window for window in acceptable if _minutes(_value(window, "start_time")) <= start and _minutes(_value(window, "end_time")) >= end]
        avoid_overlap = any(start < _minutes(_value(window, "end_time")) and end > _minutes(_value(window, "start_time")) for window in avoided)
        if avoid_overlap and not full:
            conflicts.append(MatchSlot(weekday, _clock(start), _clock(end), f"{label} потрапляє в небажаний час"))
            continue
        if full:
            if any(_preference(window) == "preferred" for window in full):
                preferred_fits += 1
            matching.append(MatchSlot(weekday, _clock(start), _clock(end), f"{label} — підходить"))
            if avoid_overlap:
                partial.append(MatchSlot(weekday, _clock(start), _clock(end), f"{label} також перетинає небажаний час"))
            continue

        overlap_or_near = []
        for window in acceptable:
            window_start = _minutes(_value(window, "start_time"))
            window_end = _minutes(_value(window, "end_time"))
            overlaps = start < window_end and end > window_start
            distance = max(window_start - end, start - window_end, 0)
            if overlaps or distance <= 60:
                overlap_or_near.append(window)
        if overlap_or_near:
            closest = min(overlap_or_near, key=lambda window: abs(_minutes(_value(window, "start_time")) - start))
            wanted = f"{_clock(_minutes(_value(closest, 'start_time')))}–{_clock(_minutes(_value(closest, 'end_time')))}"
            partial.append(MatchSlot(weekday, _clock(start), _clock(end), f"{label}; сім’я бажає {wanted}"))
        else:
            conflicts.append(MatchSlot(weekday, _clock(start), _clock(end), f"{label} — збігів немає"))

    location_differs = bool(preferred_location_id and group_location_id and str(preferred_location_id) != str(group_location_id))
    if conflicts and not matching and not partial:
        status: MatchStatus = "conflict"
        summary = "Потрібне узгодження: збігів із побажаннями сім’ї немає."
    elif conflicts or partial or location_differs or (matching and preferred_fits == 0):
        status = "partial"
        reasons = []
        if location_differs:
            reasons.append("бажана локація відрізняється")
        if partial or conflicts:
            reasons.append("частина часу потребує узгодження")
        if matching and preferred_fits == 0:
            reasons.append("час позначений лише як можливий")
        summary = "Частковий збіг: " + "; ".join(reasons) + "."
    else:
        status = "match"
        summary = "Графік підходить до побажань сім’ї."
    return ScheduleMatchResult(status, matching, partial, conflicts, summary)


def describe_preferences(windows: Iterable) -> str:
    labels = []
    for window in windows:
        day = DAY_NAMES[int(_value(window, "weekday"))]
        labels.append(f"{day} {_clock(_minutes(_value(window, 'start_time')))}–{_clock(_minutes(_value(window, 'end_time')))}")
    return "; ".join(labels) or "не вказано"


def describe_group(slots: Iterable) -> str:
    labels = []
    for slot in slots:
        start = _minutes(_value(slot, "start_time"))
        end = start + int(_value(slot, "duration_minutes"))
        labels.append(f"{DAY_NAMES[int(_value(slot, 'weekday'))]} {_clock(start)}–{_clock(end)}")
    return "; ".join(labels) or "не вказано"


def enrollment_schedule_note(result: ScheduleMatchResult, slots: Iterable, windows: Iterable) -> str:
    status = {"match": "повний", "partial": "частковий", "conflict": "потрібне узгодження", "unknown": "невідомий"}[result.status]
    suffix = " Потрібно підтвердити фінальний графік з батьками." if result.status != "match" else ""
    details = " ".join(item.detail + "." for item in [*result.matching_slots, *result.partial_slots, *result.conflicting_slots])
    return f"Побажання сім’ї: {describe_preferences(windows)}. Група: {describe_group(slots)}. Збіг: {status}. {details}{suffix}".strip()
