"""Web: the Flask app and pages

Only adapts the services and framework to HTTP and HTML. Nothing outside
this package imports Flask.
"""

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
