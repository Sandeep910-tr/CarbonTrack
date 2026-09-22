"""Centralized Notification Engine (spec sections 18-25, 44-45).

Every notification in the system MUST be created through `notify()` here
rather than by constructing `Notification(...)` directly. This is what
makes the categories/priorities consistent across every call site and is
where the dedup/cooldown logic that prevents notification spam lives.

    Event
     v
    notify()  <-- this module
     v
    Notification row (database)
     v
    GET /driver|admin/notifications  (frontend polls/reads)
     v
    Toast / Notification Center / Critical Alert (frontend, by priority)

Canonical taxonomy (do not invent new notif_type/priority values):
    notif_type: TRIP, WEATHER, VEHICLE, CARBON, SYSTEM
    priority:   INFO, ACTION, WARNING, CRITICAL
`category` remains a free-form, finer-grained label under one of the five
notif_types (e.g. notif_type=TRIP, category="route_deviation") purely for
display/filtering; it carries no behavior of its own.
"""
from datetime import timedelta
from models.db import db, Notification, utcnow

NOTIF_TYPES = ("TRIP", "WEATHER", "VEHICLE", "CARBON", "SYSTEM")
PRIORITIES = ("INFO", "ACTION", "WARNING", "CRITICAL")

# priority -> legacy severity string, kept in sync for any old code/UI still reading `severity`
_PRIORITY_TO_SEVERITY = {
    "INFO": "info",
    "ACTION": "action",
    "WARNING": "warning",
    "CRITICAL": "critical",
}

DEFAULT_COOLDOWN_MINUTES = 30


def notify(
    audience,
    notif_type,
    priority,
    title,
    message,
    driver_id=None,
    trip_id=None,
    vehicle_id=None,
    category=None,
    action_type=None,
    dedup_key=None,
    cooldown_minutes=DEFAULT_COOLDOWN_MINUTES,
):
    """Create (or suppress, if deduped) a notification.

    Returns the Notification instance if one was created/reused, or None if
    suppressed as a duplicate. Caller is still responsible for
    `db.session.commit()` (this only adds to the session), matching how the
    rest of the codebase batches notification writes with the surrounding
    transaction.

    Dedup rules (section 44 - "do not generate repeated notifications for
    the same event"):
      - If `dedup_key` is given and an ACTIVE notification with the same key
        already exists, no new row is created (the event is still ongoing).
      - If the previous one with that key is inactive (resolved) but was
        created within `cooldown_minutes`, still suppress — avoids rapid
        flap (e.g. GPS jitter around a threshold) from re-notifying.
      - Otherwise a fresh row is created and marked active.
    Pass `dedup_key=None` for one-off events that should never be deduped
    (e.g. "trip started").
    """
    if notif_type not in NOTIF_TYPES:
        raise ValueError(f"Invalid notif_type '{notif_type}', must be one of {NOTIF_TYPES}")
    if priority not in PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}', must be one of {PRIORITIES}")

    if dedup_key:
        existing = (
            Notification.query.filter_by(dedup_key=dedup_key)
            .order_by(Notification.created_at.desc())
            .first()
        )
        if existing:
            if existing.active:
                return None  # event still open, don't duplicate
            if existing.created_at and existing.created_at > utcnow() - timedelta(minutes=cooldown_minutes):
                return None  # recently resolved, within cooldown - avoid flapping

    note = Notification(
        audience=audience,
        driver_id=driver_id,
        trip_id=trip_id,
        vehicle_id=vehicle_id,
        category=category or notif_type.lower(),
        notif_type=notif_type,
        title=title,
        message=message,
        severity=_PRIORITY_TO_SEVERITY[priority],
        priority=priority,
        action_type=action_type,
        dedup_key=dedup_key,
        active=True,
    )
    db.session.add(note)
    return note


def resolve(dedup_key):
    """Mark any ACTIVE notification(s) under `dedup_key` as resolved, so a
    genuinely new occurrence of the same event can fire again later (after
    the cooldown). Does not delete history. Caller commits."""
    if not dedup_key:
        return
    Notification.query.filter_by(dedup_key=dedup_key, active=True).update({"active": False})


def unread_count(*, driver_id=None, audience=None):
    q = Notification.query.filter_by(is_read=False)
    if driver_id is not None:
        q = q.filter((Notification.driver_id == driver_id) | (Notification.audience == "all"))
    if audience is not None:
        q = q.filter(Notification.audience.in_([audience, "all"]))
    return q.count()


def mark_read(notification_ids, *, driver_id=None, audience=None):
    """Mark specific notification ids as read, scoped to the caller so a
    driver/admin can't mark someone else's notification read."""
    q = Notification.query.filter(Notification.id.in_(notification_ids))
    if driver_id is not None:
        q = q.filter((Notification.driver_id == driver_id) | (Notification.audience == "all"))
    if audience is not None:
        q = q.filter(Notification.audience.in_([audience, "all"]))
    q.update({"is_read": True}, synchronize_session=False)


def mark_all_read(*, driver_id=None, audience=None):
    q = Notification.query.filter_by(is_read=False)
    if driver_id is not None:
        q = q.filter((Notification.driver_id == driver_id) | (Notification.audience == "all"))
    if audience is not None:
        q = q.filter(Notification.audience.in_([audience, "all"]))
    q.update({"is_read": True}, synchronize_session=False)
