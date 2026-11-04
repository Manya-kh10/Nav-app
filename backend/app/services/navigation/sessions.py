import time
import uuid
from dataclasses import dataclass, field

from app.schemas.nav_state import NavStatus
from app.schemas.route import Instruction, LatLon, Route
from app.services.navigation.announcer import AnnouncementState
from app.services.routing.deviation import DeviationTracker
from app.services.traffic.provider import TrafficSnapshot

TTL_S = 2 * 3600
MAX_SESSIONS = 200


@dataclass
class Session:
    route: Route
    instructions: list[Instruction]
    landmarks: dict[int, dict]
    destination: LatLon
    mode: str
    tracker: DeviationTracker = field(default_factory=DeviationTracker)
    announcer_state: AnnouncementState = field(default_factory=AnnouncementState)
    traffic_snapshot: TrafficSnapshot = field(default_factory=TrafficSnapshot)
    last_ts: float = 0.0
    last_fix: tuple[float, float, float] | None = None  # (lat, lon, timestamp)
    speed_mps: float = 0.0
    driver_lang: str = "en"
    reroute_seq: int = 0
    last_reroute: float = 0.0
    last_status: NavStatus | None = None
    last_status_at: float = 0.0
    last_answer: tuple[str, str] | None = None   # (text, lang) for "repeat"
    created: float = field(default_factory=time.time)


_sessions: dict[str, Session] = {}


def _prune() -> None:
    now = time.time()
    for sid in [k for k, s in _sessions.items() if now - s.created > TTL_S]:
        del _sessions[sid]
    while len(_sessions) >= MAX_SESSIONS:
        del _sessions[min(_sessions, key=lambda k: _sessions[k].created)]


def create_session(route, instructions, landmarks, destination, mode, traffic_snapshot=None) -> str:
    _prune()
    sid = uuid.uuid4().hex
    s = Session(route, instructions, landmarks, destination, mode)
    if traffic_snapshot:
        s.traffic_snapshot = traffic_snapshot
    _sessions[sid] = s
    return sid


def get_session(sid: str) -> Session | None:
    s = _sessions.get(sid)
    if s and time.time() - s.created > TTL_S:
        del _sessions[sid]
        return None
    return s
