"""Create or restore a portable AURA data backup.

Secrets and model files are intentionally excluded. SQLite is copied through
the SQLite backup API so an online backup is transactionally consistent.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_db = sqlite3.connect(source)
    try:
        target_db = sqlite3.connect(destination)
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
    finally:
        source_db.close()


def create_backup(settings: Settings, archive: Path) -> None:
    settings.init_dirs()
    archive = archive.resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aura-backup-") as temporary:
        root = Path(temporary)
        _sqlite_backup(settings.db_path, root / "aura.db")
        for name, path in (("uploads", settings.uploads_dir), ("chroma_db", settings.chroma_path)):
            if path.exists():
                shutil.copytree(path, root / name)
        with tarfile.open(archive, "w:gz") as output:
            for item in root.iterdir():
                output.add(item, arcname=item.name)


def restore_backup(settings: Settings, archive: Path) -> None:
    settings.init_dirs()
    with tempfile.TemporaryDirectory(prefix="aura-restore-") as temporary:
        root = Path(temporary)
        with tarfile.open(archive, "r:gz") as source:
            for member in source.getmembers():
                if member.issym() or member.islnk():
                    raise RuntimeError("Backup contains an unsupported link")
                target = (root / member.name).resolve()
                if os.path.commonpath((str(root.resolve()), str(target))) != str(root.resolve()):
                    raise RuntimeError("Backup contains an unsafe path")
            source.extractall(root)
        restored_db = root / "aura.db"
        if not restored_db.is_file():
            raise RuntimeError("Backup does not contain aura.db")
        # Restore through SQLite's backup API rather than replacing the path;
        # this is portable to Windows and remains safe when a process has the
        # database opened in read-only mode. Operators should still stop AURA
        # before a production restore.
        _sqlite_backup(restored_db, settings.db_path)
        for name, destination in (("uploads", settings.uploads_dir), ("chroma_db", settings.chroma_path)):
            source_dir = root / name
            if source_dir.exists():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source_dir, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up or restore AURA persistent data")
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    settings = Settings()
    if args.operation == "backup":
        create_backup(settings, args.archive)
    else:
        restore_backup(settings, args.archive)
    print(f"AURA {args.operation} completed: {args.archive.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
