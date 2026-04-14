import re

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
VALID_USERNAME = 'newsband'
VALID_PASSWORD = 'Journalism'
LOGO_URL = "https://raw.githubusercontent.com/Manas236/Newsband/main/newsband-logo-0022.png"

# ─────────────────────────────────────────────
# File Paths & URLs
# ─────────────────────────────────────────────
GITHUB_BASE = "https://raw.githubusercontent.com/Manas236/Newsband/main/"

# ─────────────────────────────────────────────
# Multi-Template Configuration
# ─────────────────────────────────────────────
TEMPLATES_CONFIG = {
    "1": {
        "name": "Template Editor 1",
        "file": "Day6Temp.html",
        "image": "Day6Temp.png",
        "has_alignment": True
    },
    "2": {
        "name": "Template Editor 2",
        "file": "template1.html",
        "image": "template1.png",
        "has_alignment": False
    }
}

# Default for legacy code support if needed
ORIGINAL_FILE = TEMPLATES_CONFIG["1"]["file"]

# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────
SECRET_KEY = 'newsband-secret-key-2024'
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB limit
ALLOWED_EXTENSIONS = {"html", "htm"}

# ─────────────────────────────────────────────
# HTML Processing Constants
# ─────────────────────────────────────────────
TEXT_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "td", "span", "strong"}
ALL_EDITABLE = TEXT_TAGS | {"img", "a"}

FOOTER_SECTION_KEYWORDS = {"footer"}
SIDEBAR_SECTION_KEYWORDS = {"sidebar"}

_SIDEBAR_ALLOWED_RE = re.compile(
    r'rni'
    r'|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
    r'|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?'
    r'|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    r'|\b\d{1,2}\b'
    r'|\b20\d{2}\b',
    re.I,
)
