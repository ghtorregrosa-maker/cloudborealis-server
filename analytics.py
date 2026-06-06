"""analytics.py â€” Analytics en tiempo real."""
from __future__ import annotations
import json, threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import config

ANALYTICS_FILE = config.DATA_DIR / "analytics.json"

def _now(): return datetime.utcnow().isoformat()
def _load():
    if ANALYTICS_FILE.exists():
        try: return json.loads(ANALYTICS_FILE.read_text(encoding="utf-8"))
        except: pass
    return {"events": [], "totals": {"visits": 0, "messages": 0, "users": 0}}
def _save(data):
    ANALYTICS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

class Analytics:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = _load()
        print("[Analytics] Sistema de analytics listo.")

    def track_visit(self, user_id, ip="", user_agent=""):
        event = {"type":"visit","user_id":user_id,"ip":ip[:15] if ip else "",
                 "device":self._detect_device(user_agent),"timestamp":_now()}
        with self._lock:
            self._data["events"].append(event)
            self._data["totals"]["visits"] += 1
            if len(self._data["events"]) > 5000:
                self._data["events"] = self._data["events"][-5000:]
            _save(self._data)

    def track_message(self, user_id, question, response_time_ms=0):
        event = {"type":"message","user_id":user_id,"question":question[:100],
                 "response_time_ms":response_time_ms,"timestamp":_now()}
        with self._lock:
            self._data["events"].append(event)
            self._data["totals"]["messages"] += 1
            _save(self._data)

    def track_login(self, username, success):
        event = {"type":"login","username":username,"success":success,"timestamp":_now()}
        with self._lock:
            self._data["events"].append(event)
            if success: self._data["totals"]["users"] += 1
            _save(self._data)

    def get_dashboard_data(self, hours=24):
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self._lock:
            events = list(self._data["events"])
            totals = dict(self._data["totals"])
        recent   = [e for e in events if self._is_recent(e, cutoff)]
        visits   = [e for e in recent if e["type"] == "visit"]
        messages = [e for e in recent if e["type"] == "message"]
        questions = Counter(e.get("question","") for e in messages if e.get("question"))
        devices   = Counter(e.get("device","unknown") for e in visits)
        hourly    = defaultdict(int)
        for e in visits:
            try: hourly[datetime.fromisoformat(e["timestamp"]).strftime("%H:00")] += 1
            except: pass
        times = [e.get("response_time_ms",0) for e in messages if e.get("response_time_ms")]
        return {
            "totals": totals, "recent_hours": hours,
            "recent_visits": len(visits), "recent_messages": len(messages),
            "unique_users": len(set(e.get("user_id","") for e in recent)),
            "top_questions": questions.most_common(10),
            "devices": dict(devices), "hourly_visits": dict(sorted(hourly.items())),
            "avg_response_ms": round(sum(times)/len(times)) if times else 0,
            "recent_events": recent[-20:],
        }

    def _is_recent(self, e, cutoff):
        try: return datetime.fromisoformat(e["timestamp"]) >= cutoff
        except: return True

    def _detect_device(self, ua):
        ua = ua.lower()
        if "mobile" in ua or "android" in ua or "iphone" in ua: return "mobile"
        if "tablet" in ua or "ipad" in ua: return "tablet"
        return "desktop"

_analytics_instance = None
def get_analytics():
    global _analytics_instance
    if _analytics_instance is None: _analytics_instance = Analytics()
    return _analytics_instance
