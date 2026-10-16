"""Calendar management use cases — activate plans, skip days, push back."""

from __future__ import annotations

from datetime import date, timedelta

from fitness.adapters.persistence.json_plan_store import JsonPlanStore
from fitness.application.ports.clock import Clock
from fitness.domain.workout_plan import ActiveCalendar, CalendarEntry

SCHEDULE_DAYS = 56


class ManageCalendarUseCase:
    def __init__(self, plan_store: JsonPlanStore, clock: Clock) -> None:
        self._store = plan_store
        self._clock = clock

    def activate_plan(self, plan_id: str) -> ActiveCalendar | None:
        plan = self._store.get_plan(plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        today_str = today.isoformat()
        old_cal = self._store.load_calendar()
        past_entries = []
        kept_today = None
        if old_cal:
            old_plan = self._store.get_plan(old_cal.plan_id)

            def _pin_label(entry):
                """Freeze the old plan's label so history keeps reading correctly."""
                if old_plan and entry.saved_label is None:
                    rot = old_plan.rotation
                    entry.saved_label = rot[entry.day_index % len(rot)].label
                return entry

            for e in old_cal.entries:
                if e.status == "planned":
                    continue           # unstarted days are replaced by the new plan
                if e.date < today_str:
                    past_entries.append(_pin_label(e))
                elif e.date == today_str:
                    # Work already done today survives a plan switch too.
                    kept_today = _pin_label(e)

        # Only generate from tomorrow when today's entry is being preserved,
        # otherwise the day would appear twice.
        start = today + timedelta(days=1) if kept_today else today
        new_entries = _generate_entries(plan.rotation, start, SCHEDULE_DAYS)
        cal = ActiveCalendar(
            plan_id=plan.id,
            plan_name=plan.name,
            entries=past_entries + ([kept_today] if kept_today else []) + new_entries,
        )
        self._store.save_calendar(cal)
        return cal

    def get_calendar(self) -> dict | None:
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        _extend_if_needed(cal, plan.rotation, today)
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, today)

    def skip_day(self) -> dict | None:
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        _extend_if_needed(cal, plan.rotation, self._clock.today())
        today_str = self._clock.today().isoformat()
        today_entry = _find_entry(cal, today_str)
        if today_entry is None:
            return None
        today_entry.status = "skipped"
        _regenerate_future(cal, plan.rotation, self._clock.today())
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, self._clock.today())

    def push_back(self) -> dict | None:
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        _extend_if_needed(cal, plan.rotation, today)
        today_str = today.isoformat()
        today_entry = _find_entry(cal, today_str)
        if today_entry is None:
            return None
        saved_index = today_entry.day_index
        today_entry.status = "skipped"
        future = [e for e in cal.entries if e.date > today_str and e.status == "planned"]
        future.sort(key=lambda e: e.date)
        prev_index = saved_index
        for entry in future:
            old_index = entry.day_index
            entry.day_index = prev_index
            prev_index = old_index
        _extend_if_needed(cal, plan.rotation, today)
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, self._clock.today())

    def complete_day(self) -> dict | None:
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today_str = self._clock.today().isoformat()
        entry = _find_entry(cal, today_str)
        if entry is not None:
            entry.status = "completed"
            self._store.save_calendar(cal)
        return _calendar_view(cal, plan, self._clock.today())

    def align(self, day_index: int) -> dict | None:
        """Align the calendar so today maps to a specific rotation day_index."""
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        _extend_if_needed(cal, plan.rotation, today)
        today_entry = _find_entry(cal, today.isoformat())
        if today_entry is None:
            return None
        offset = day_index - today_entry.day_index
        for entry in cal.entries:
            if entry.date >= today.isoformat() and entry.status == "planned":
                entry.day_index = (entry.day_index + offset) % len(plan.rotation)
        # Only relabel today if it hasn't happened yet. A completed or skipped day
        # is history — the rotation realigns around it, from tomorrow onward, but
        # what it was recorded as doesn't change.
        if today_entry.status == "planned":
            today_entry.day_index = day_index
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, today)

    def skip_to_today(self) -> tuple[dict, int] | None:
        """Skip all missed (past planned) days at once, landing on today."""
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        today_str = today.isoformat()
        skipped = 0
        for entry in cal.entries:
            if entry.date < today_str and entry.status == "planned":
                entry.status = "skipped"
                skipped += 1
        _extend_if_needed(cal, plan.rotation, today)
        _regenerate_future(cal, plan.rotation, today)
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, today), skipped

    def push_back_to_today(self) -> tuple[dict, int] | None:
        """Push back all missed (past planned) days, shifting them forward to today."""
        self._store.save_calendar_snapshot()
        cal = self._store.load_calendar()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        today = self._clock.today()
        today_str = today.isoformat()
        missed = [e for e in cal.entries if e.date < today_str and e.status == "planned"]
        for entry in missed:
            entry.status = "skipped"
        _extend_if_needed(cal, plan.rotation, today)
        if not missed:
            return _calendar_view(cal, plan, today), 0
        first_missed = missed[0]
        saved_index = first_missed.day_index
        future = [e for e in cal.entries if e.date >= today_str and e.status == "planned"]
        future.sort(key=lambda e: e.date)
        prev_index = saved_index
        for entry in future:
            old_index = entry.day_index
            entry.day_index = prev_index
            prev_index = old_index
        self._store.save_calendar(cal)
        return _calendar_view(cal, plan, today), len(missed)

    def undo(self) -> dict | None:
        cal = self._store.restore_calendar_snapshot()
        if cal is None:
            return None
        plan = self._store.get_plan(cal.plan_id)
        if plan is None:
            return None
        return _calendar_view(cal, plan, self._clock.today())


def _generate_entries(
    rotation: tuple, start: date, days: int
) -> list[CalendarEntry]:
    entries = []
    for i in range(days):
        d = start + timedelta(days=i)
        entries.append(CalendarEntry(
            date=d.isoformat(),
            day_index=i % len(rotation),
            status="planned",
        ))
    return entries


def _find_entry(cal: ActiveCalendar, date_str: str) -> CalendarEntry | None:
    for e in cal.entries:
        if e.date == date_str:
            return e
    return None


def _regenerate_future(
    cal: ActiveCalendar, rotation: tuple, today: date
) -> None:
    today_str = today.isoformat()
    past = [e for e in cal.entries if e.date <= today_str]
    last_settled = past[-1] if past else None
    next_index = ((last_settled.day_index + 1) % len(rotation)) if last_settled else 0
    future_dates = []
    max_date = today + timedelta(days=SCHEDULE_DAYS)
    d = today + timedelta(days=1)
    while d <= max_date:
        future_dates.append(d)
        d += timedelta(days=1)
    new_future = []
    for i, fd in enumerate(future_dates):
        new_future.append(CalendarEntry(
            date=fd.isoformat(),
            day_index=(next_index + i) % len(rotation),
            status="planned",
        ))
    cal.entries = past + new_future


def _extend_if_needed(
    cal: ActiveCalendar, rotation: tuple, today: date
) -> None:
    if not cal.entries:
        return
    last_date = date.fromisoformat(cal.entries[-1].date)
    horizon = today + timedelta(days=SCHEDULE_DAYS)
    if last_date >= horizon:
        return
    last_index = cal.entries[-1].day_index
    d = last_date + timedelta(days=1)
    while d <= horizon:
        last_index = (last_index + 1) % len(rotation)
        cal.entries.append(CalendarEntry(
            date=d.isoformat(), day_index=last_index, status="planned",
        ))
        d += timedelta(days=1)
    cal.entries = [e for e in cal.entries if e.date >= today.isoformat() or e.status != "planned"]


def _calendar_view(
    cal: ActiveCalendar, plan, today: date
) -> dict:
    today_str = today.isoformat()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    entries_out = []
    for e in cal.entries:
        if e.date < today_str and e.status == "planned":
            continue
        rotation_day = plan.rotation[e.day_index % len(plan.rotation)]
        label = e.saved_label if e.saved_label else rotation_day.label
        is_rest = rotation_day.is_rest if not e.saved_label else False
        exercises = [ex.to_dict() for ex in rotation_day.exercises] if not e.saved_label else []
        entries_out.append({
            "date": e.date,
            "label": label,
            "is_rest": is_rest,
            "is_today": e.date == today_str,
            "status": e.status,
            "exercises": exercises,
        })
    rotation_options = [
        {"index": i, "label": d.label, "is_rest": d.is_rest}
        for i, d in enumerate(plan.rotation)
    ]
    seen_labels = set()
    unique_rotation = []
    for opt in rotation_options:
        if opt["label"] not in seen_labels:
            seen_labels.add(opt["label"])
            unique_rotation.append(opt)

    return {
        "plan_id": cal.plan_id,
        "plan_name": cal.plan_name,
        "today": today_str,
        "entries": entries_out[:SCHEDULE_DAYS],
        "rotation": unique_rotation,
    }
