import asyncio
import os
import pytest
from agentos.skills.filesystem import FilesystemSkill


def test_filesystem_search_supports_glob_fallback_and_reports_errors(tmp_path):
    # Setup allowed root and a file to search
    allowed_root = tmp_path / "proyects"
    allowed_root.mkdir()
    
    custom_file = allowed_root / "test.custom"
    custom_file.write_text("my-secret-key = 12345", encoding="utf-8")
    
    python_file = allowed_root / "test.py"
    python_file.write_text("def my_func(): pass", encoding="utf-8")

    # Instantiate skill withallowed root
    skill = FilesystemSkill(config={"allowed_roots": [str(allowed_root)]})

    res_py = asyncio.run(skill.search(str(allowed_root), "my_func", "*.py"))
    assert res_py.success
    
    # Test 2: Custom extension search (should fallback to glob and find it)
    res_custom = asyncio.run(skill.search(str(allowed_root), "my-secret-key", "*.custom"))
    assert res_custom.success
    assert len(res_custom.data["matches"]) == 1
    assert res_custom.data["matches"][0]["content"] == "my-secret-key = 12345"

    # Test 3: Language alias mapping (javascript -> js)
    js_file = allowed_root / "test.js"
    js_file.write_text("function myJs() {}", encoding="utf-8")
    res_js = asyncio.run(skill.search(str(allowed_root), "myJs", "javascript"))
    assert res_js.success
    assert len(res_js.data["matches"]) == 1

    # Test 4: Verify error propagation for invalid ripgrep arguments
    # passing a non-existent path to trigger ripgrep error
    res_err = asyncio.run(skill.search(str(allowed_root / "non_existent_folder"), "test", "*.py"))
    assert not res_err.success
    assert "ripgrep failed" in res_err.error or "not within allowed roots" in res_err.error
