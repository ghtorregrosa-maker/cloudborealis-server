"""
CloudBorealisAssistant - Configuración global del sistema
"""

import os
from pathlib import Path

# ─── Rutas base ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

MEMORY_FILE      = DATA_DIR / "memory.json"
EXPERIENCES_FILE = DATA_DIR / "experiences.json"
CORRECTIONS_FILE = DATA_DIR / "corrections.json"
LOGS_FILE        = DATA_DIR / "logs.json"

# ─── Servidor / Cliente ───────────────────────────────────────────────────────
SERVER_HOST = os.getenv("CB_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("CB_SERVER_PORT", "8000"))
CLIENT_BASE_URL = os.getenv("CB_CLIENT_URL", f"http://127.0.0.1:{SERVER_PORT}")
API_SECRET_KEY  = os.getenv("CB_API_SECRET", "cloudborealis-secret-2025")

# ─── APIs de redes sociales ───────────────────────────────────────────────────
TWITTER_BEARER_TOKEN    = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_KEY         = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET      = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN    = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET   = os.getenv("TWITTER_ACCESS_SECRET", "")

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "CloudBorealisBot/1.0")
REDDIT_USERNAME      = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = os.getenv("REDDIT_PASSWORD", "")

# ─── Anthropic (NLP mejorado) ─────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─── Configuración de seguridad ───────────────────────────────────────────────
ALLOWED_PROGRAMS = [
    "notepad", "calc", "explorer", "chrome", "firefox", "edge",
    "code", "python", "cmd", "powershell", "vlc", "spotify",
]
BLOCKED_PATHS = [
    "C:\\Windows\\System32",
    "/etc/passwd",
    "/etc/shadow",
]
MAX_RETRIES_BEFORE_BLOCK = 3     # Bloquear acción tras N fallos iguales
PATTERN_WINDOW_HOURS     = 24    # Ventana para detectar patrones de error

# ─── Dashboard ────────────────────────────────────────────────────────────────
DASHBOARD_REFRESH_SECS = 30
LOG_MAX_DISPLAY        = 100

# ─── Versión ──────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
APP_NAME = "CloudBorealisAssistant"
