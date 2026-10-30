"""Vercel entrypoint for the read-only CustomerPulse API.

Vercel's FastAPI runtime looks for an ``app`` object in ``app.py`` at the
project root (here, ``backend/``). The package lives in ``src/``, so it is
put on the import path before importing. Only core (API) dependencies are
installed on Vercel; the analysis extras are never needed to serve requests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from customerpulse.api.app import app  # noqa: E402

__all__ = ["app"]
