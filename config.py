"""LLMNotes Configuration"""

import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(BASE_DIR, "notes")
SOURCES_DIR = os.path.join(BASE_DIR, "sources")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
DB_PATH = os.path.join(STORAGE_DIR, "llmnotes.db")

# Ensure directories exist
for d in [NOTES_DIR, SOURCES_DIR, STORAGE_DIR]:
    os.makedirs(d, exist_ok=True)

# OpenRouter Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
OPENROUTER_QUICK_MODEL = os.environ.get("OPENROUTER_QUICK_MODEL", "openai/gpt-4o-mini")

# Supported file types
SUPPORTED_EXTENSIONS = {".md", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}