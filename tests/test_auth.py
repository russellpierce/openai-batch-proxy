import tempfile
from pathlib import Path

import pytest

from openai_batch_proxy.auth import load_api_keys


def test_load_api_keys_success() -> None:
    """Test loading API keys from file."""
    content = """sk-key1
# comment
sk-key2

sk-key3
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        keys = load_api_keys(temp_path)
        assert len(keys) == 3
        assert "sk-key1" in keys
        assert "sk-key2" in keys
        assert "sk-key3" in keys
    finally:
        temp_path.unlink()


def test_load_api_keys_missing_file() -> None:
    """Test that missing file causes exit."""
    with pytest.raises(SystemExit):
        load_api_keys("/nonexistent/keys.txt")


def test_load_api_keys_empty_file() -> None:
    """Test that empty file causes exit."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("# only comments\n\n")
        temp_path = Path(f.name)

    try:
        with pytest.raises(SystemExit):
            load_api_keys(temp_path)
    finally:
        temp_path.unlink()
