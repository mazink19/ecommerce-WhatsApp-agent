"""Shared isolated database configuration for tests."""

import os
import tempfile
from pathlib import Path


TEST_DB = Path(tempfile.mkdtemp(prefix="ecommerce-agent-tests-")) / "store.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
