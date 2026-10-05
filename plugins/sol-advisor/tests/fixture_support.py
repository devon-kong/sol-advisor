"""Private temporary scratch; explicit parents remain supported for compatibility."""
from pathlib import Path
import stat
import tempfile


def fixture_directory(parent: Path | None = None) -> tempfile.TemporaryDirectory:
    if parent is None:
        return tempfile.TemporaryDirectory(prefix="sol-advisor-test.", dir=Path(tempfile.gettempdir()).resolve())
    parent.mkdir(mode=0o700, exist_ok=True)
    if not stat.S_ISDIR(parent.lstat().st_mode):
        raise ValueError(f"fixture parent must be a real directory: {parent}")
    return tempfile.TemporaryDirectory(dir=parent)
