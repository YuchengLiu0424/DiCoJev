import importlib.util
from pathlib import Path


def test_documentation_ownership_map_targets_exist():
    path = Path(__file__).parents[1] / "scripts" / "check_doc_ownership.py"
    spec = importlib.util.spec_from_file_location("check_doc_ownership", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.validate() == []
