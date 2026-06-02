from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from unilabos.registry.ast_registry_scanner import scan_directory  # noqa: E402


def test_virtual_workbench_device_ids_are_unique():
    virtual_file = REPO_ROOT / "unilabos/devices/virtual/workbench.py"
    ai4m_file = REPO_ROOT / "unilabos/devices/workstation/AI4M/workbench.py"

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = scan_directory(
            REPO_ROOT / "unilabos/devices",
            python_path=REPO_ROOT,
            executor=executor,
            include_files=[virtual_file, ai4m_file],
        )

    assert "virtual_workbench" in result["devices"]
    assert "AI4M_virtual_workbench" in result["devices"]
