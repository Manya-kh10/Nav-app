"""Daily Budget Tracker for Traffic API Calls.
Enforces hard daily limits to stay safely within TomTom free-tier quotas (default 400 calls/day).
Persists call counts and resets automatically each UTC day.
"""

import json
import threading
from datetime import datetime, timezone

from app.core.config import ROOT, settings

_USAGE_FILE = ROOT / "data" / "traffic_usage.json"
_lock = threading.Lock()

_current_date: str = ""
_calls_today: int = 0


def _get_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_state() -> None:
    global _current_date, _calls_today
    today = _get_today_str()
    if _current_date != today:
        _current_date = today
        _calls_today = 0
        if _USAGE_FILE.exists():
            try:
                data = json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
                if data.get("date") == today:
                    _calls_today = int(data.get("calls_today", 0))
            except Exception:
                _calls_today = 0


def _save_state() -> None:
    try:
        _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _USAGE_FILE.write_text(
            json.dumps({"date": _current_date, "calls_today": _calls_today}),
            encoding="utf-8",
        )
    except Exception:
        pass


def can_call() -> bool:
    """Returns True if traffic calls are within the daily quota."""
    with _lock:
        _load_state()
        return _calls_today < settings.traffic_daily_cap


def record_call(endpoint: str, status_code: int = 200) -> None:
    """Records an executed traffic API call."""
    global _calls_today
    with _lock:
        _load_state()
        _calls_today += 1
        _save_state()


def get_usage() -> dict:
    """Returns current traffic budget usage statistics."""
    with _lock:
        _load_state()
        cap = settings.traffic_daily_cap
        return {
            "date": _current_date,
            "calls_today": _calls_today,
            "daily_cap": cap,
            "remaining": max(0, cap - _calls_today),
            "cap_reached": _calls_today >= cap,
        }


def reset_for_test(calls: int = 0) -> None:
    """Helper for testing budget limit enforcement."""
    global _calls_today, _current_date
    with _lock:
        _current_date = _get_today_str()
        _calls_today = calls
        _save_state()

