"""
EduConnect settings package initializer.
Dynamically imports development or production settings based on DJANGO_ENV.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file before inspecting environment
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

env = os.getenv("DJANGO_ENV", "development").lower()

if env == "production":
    from .production import *
else:
    from .development import *
