import os
import sys
from pathlib import Path

# Enforce zero-network offline mode and clean base url during test runs
os.environ["DEMO_MODE"] = "offline"
os.environ["LLM_BASE_URL"] = ""

BACKEND_ROOT = Path(__file__).parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

# Backend tests import ``app`` from the backend project and also exercise the
# offline-only training utilities under the repository-level ``ml_training/``
# package.  Keep both concerns importable regardless of whether pytest is
# launched from the repository root or with ``--project backend``.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))
