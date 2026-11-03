import json
import threading
import time
from collections import Counter

from app.core.config import ROOT

_LOG = ROOT / "data" / "usage.jsonl"
_counts: Counter = Counter()
_lock = threading.Lock()


def record(kind: str, **info) -> None:
    with _lock:
        _counts[kind] += 1
        try:
            _LOG.parent.mkdir(parents=True, exist_ok=True)
            with _LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time()), "kind": kind, **info}) + "\n")
        except OSError:
            pass


def summary() -> dict:
    with _lock:
        return dict(_counts)