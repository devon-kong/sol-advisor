"""Repository-local scratch allocation shared by the three protocol fixtures."""
from pathlib import Path
import stat
import tempfile


def fixture_directory(parent: Path) -> tempfile.TemporaryDirectory:
    parent.mkdir(mode=0o700, exist_ok=True)
    if not stat.S_ISDIR(parent.lstat().st_mode):
        raise ValueError(f"fixture parent must be a real directory: {parent}")
    return tempfile.TemporaryDirectory(dir=parent)
