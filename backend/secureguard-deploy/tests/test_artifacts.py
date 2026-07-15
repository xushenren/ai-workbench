"""tests/test_artifacts.py — 代码块提取 + Artifact（问题3）。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.artifacts import extract_artifacts, first_python, build_readme, format_verify


def test_extract_python_block():
    txt = "示例：\n```python\nprint('hi')\n```\n"
    arts = extract_artifacts(txt)
    assert len(arts) == 1 and arts[0].language == "python"
    assert arts[0].filename.endswith(".py") and arts[0].runnable is True


def test_extract_multiple_langs():
    txt = "```python\nx=1\n```\n```html\n<div></div>\n```"
    arts = extract_artifacts(txt)
    langs = {a.language for a in arts}
    assert langs == {"python", "html"}


def test_first_python():
    assert "print" in first_python("```python\nprint(1)\n```")
    assert first_python("无代码") == ""


def test_build_readme_lists_files():
    arts = extract_artifacts("```python\nx=1\n```\n```json\n{}\n```")
    rd = build_readme(arts)
    assert rd.filename == "README.md" and "snippet_1.py" in rd.content


def test_format_verify_pass():
    s = format_verify({"available": True, "exit_code": 0, "stdout": "[1, 2, 3]",
                       "stderr": "", "duration_ms": 100, "timed_out": False, "error": ""})
    assert "✅ 通过" in s and "[1, 2, 3]" in s


def test_format_verify_unavailable():
    s = format_verify({"available": False})
    assert "未部署" in s


def test_empty_block_ignored():
    assert extract_artifacts("```python\n\n```") == []
