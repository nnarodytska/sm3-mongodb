import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The SM3-Text-to-Query checkout this repo reproduces. Parity tests need it.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM_REPO = os.environ.get(
    "SM3_UPSTREAM_REPO", os.path.join(os.path.dirname(_REPO_ROOT), "SM3-Text-to-Query")
)
UPSTREAM_LOADER = os.path.join(
    UPSTREAM_REPO, "src", "setup_dbs", "mongodb", "setup-mongodb.py"
)
UPSTREAM_CSV_DIR = os.path.join(UPSTREAM_REPO, "data", "synthea_data")


@pytest.fixture(scope="session")
def upstream_source():
    if not os.path.isfile(UPSTREAM_LOADER):
        pytest.skip(f"upstream loader not found at {UPSTREAM_LOADER}")
    with open(UPSTREAM_LOADER) as handle:
        return handle.read()


@pytest.fixture(scope="session")
def upstream_module():
    """Import upstream's setup-mongodb.py by path (the hyphen blocks a normal import)."""
    if not os.path.isfile(UPSTREAM_LOADER):
        pytest.skip(f"upstream loader not found at {UPSTREAM_LOADER}")
    import importlib.util

    spec = importlib.util.spec_from_file_location("upstream_setup_mongodb", UPSTREAM_LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def csv_dir():
    if not os.path.isdir(UPSTREAM_CSV_DIR):
        pytest.skip(f"Synthea CSVs not found at {UPSTREAM_CSV_DIR}")
    return UPSTREAM_CSV_DIR
