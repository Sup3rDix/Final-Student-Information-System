"""Safe JSON-lines persistence in plain .txt files (Python standard library only)."""

import json
import os
import tempfile
from pathlib import Path


class StorageError(Exception):
    """Raised for malformed, unreadable, or unwritable data files."""


class TextStore:
    """Each line is one JSON object in an ordinary UTF-8 .txt file."""

    def __init__(self, data_dir, name):
        self.path = Path(data_dir) / f"{name}.txt"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def load(self):
        rows = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise StorageError(
                            f"Invalid JSON in {self.path.name}, line {number}: {exc.msg}. "
                            "Fix or restore the file before editing records."
                        ) from exc
                    if not isinstance(row, dict):
                        raise StorageError(
                            f"Invalid record in {self.path.name}, line {number}: expected an object."
                        )
                    rows.append(row)
        except (OSError, UnicodeError) as exc:
            raise StorageError(f"Cannot read {self.path.name}: {exc}") from exc
        return rows

    def append(self, row):
        """True append operation for new records; check file health first."""
        self.load()  # Refuse to append to damaged data.
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, UnicodeError, TypeError) as exc:
            raise StorageError(f"Cannot append to {self.path.name}: {exc}") from exc

    def save(self, rows):
        """Atomic rewrite for updates/deletes: replaces the file only after success."""
        self.load()  # Prevent silent data loss if a file has become corrupted.
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.stem}_", suffix=".tmp", delete=False
            ) as handle:
                temp_name = handle.name
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except (OSError, UnicodeError, TypeError) as exc:
            raise StorageError(f"Cannot save {self.path.name}: {exc}") from exc
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
