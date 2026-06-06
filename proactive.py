"""proactive.py â€” Monitor proactivo de tendencias."""
from __future__ import annotations
import json, threading, time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests
import config

ALERTS_FILE  = config.DATA_DIR / "alerts.json"
MONITOR_FILE = config.DATA_DIR / "monitor_config.json"

def _now(): return datetime.utcnow().isoformat()
def _load(path):
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except: pass
    return {}
def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

class ProactiveMonitor:
    DEFAULT_TOPICS = ["inteligencia artificial","ciberseguridad","python","tecnologia"]

    def __init__(self):
        self._lock    = threading.Lock()
        self._alerts  = _load(ALERTS_FILE) if ALERTS_FILE.exists() else {"alerts": []}
        self._config  = _load(MONITOR_FILE) if MONITOR_FILE.exists() else {}
        self._running = False
        self._topics  = self._config.get("topics", self.DEFAULT_TOPICS)
        self._interval= self._config.get("interval_minutes", 30) * 60
        print("[Proactive] Monitor proactivo listo.")

    def start(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        print("[Proactive] Monitor iniciado.")

    def stop(self): self._running = False

    def _loop(self):
        while self._running:
            try: self._scan_topics()
            except Exception as e: print(f"[Proactive] Error: {e}")
            time.sleep(self._interval)

    def _scan_topics(self):
        for topic in self._topics:
            try:
                result = self._search_topic(topic)
                if result: self._create_alert(topic, result)
            except: pass

    def _search_topic(self, topic):
        try:
            resp = requests.get("https://api.duckduckgo.com/",
                params={"q":topic,"format":"json","no_html":1}, timeout=10)
            abstract = resp.json().get("AbstractText","")
            if abstract and len(abstract) > 50: return abstract[:300]
        except: pass
        return None

    def _create_alert(self, topic, content):
        alert = {"id": len(self._alerts["alerts"])+1, "topic": topic,
                 "content": content, "timestamp": _now(), "read": False,
                 "priority": "media"}
        with self._lock:
            self._alerts["alerts"].append(alert)
            if len(self._alerts["alerts"]) > 200:
                self._alerts["alerts"] = self._alerts["alerts"][-200:]
            _save(ALERTS_FILE, self._alerts)

    def get_alerts(self, unread_only=False, limit=20):
        with self._lock:
            alerts = list(self._alerts.get("alerts",[]))
        if unread_only: alerts = [a for a in alerts if not a.get("read")]
        return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def add_topic(self, topic):
        if topic not in self._topics:
            self._topics.append(topic)
            self._config["topics"] = self._topics
            _save(MONITOR_FILE, self._config)

    def get_config(self):
        return {"topics": self._topics, "interval_minutes": self._interval//60,
                "running": self._running,
                "unread": len([a for a in self._alerts.get("alerts",[]) if not a.get("read")])}

    def force_scan(self):
        self._scan_topics()
        return len(self.get_alerts(unread_only=True))

_monitor_instance = None
def get_monitor():
    global _monitor_instance
    if _monitor_instance is None: _monitor_instance = ProactiveMonitor()
    return _monitor_instance
