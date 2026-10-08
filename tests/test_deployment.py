import sqlite3
import tarfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import Settings
from backend.app.database import Base
from backend.app.models.sql_models import User
from backend.app.runtime_diagnostics import readiness_status
from scripts.backup import create_backup, restore_backup


def test_production_deployment_files_are_localhost_safe():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert '"${AURA_BIND_ADDRESS:-127.0.0.1}:${AURA_PUBLISHED_PORT:-8000}:8000"' in compose
    assert '"--workers", "1"' in dockerfile
    assert "RELOAD=false" in dockerfile
    assert "USER aura" in dockerfile
    assert "AUTH_SECRET_KEY_FILE" in compose


def test_readiness_is_not_ready_when_database_schema_is_unavailable(monkeypatch):
    monkeypatch.setattr("backend.app.runtime_diagnostics.database.schema_status", lambda: {"ready": False, "version": 0, "missing": ["tasks"]})
    result = readiness_status()
    assert result["status"] == "unavailable"
    assert result["core"]["database"]["state"] == "schema_incomplete"


def test_backup_restore_uses_sqlite_backup_and_preserves_uploads(tmp_path):
    settings = Settings(
        _env_file=None,
        BASE_DIR=tmp_path,
        DATA_DIR=tmp_path / "data",
        MODELS_DIR=tmp_path / "models",
        DB_PATH=tmp_path / "data" / "aura.db",
        ENVIRONMENT="test",
    )
    settings.init_dirs()
    engine = create_engine(settings.resolved_database_url)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(name="Backup User", preferences="{}", settings={}))
    session.commit()
    session.close()
    (settings.uploads_dir / "note.txt").write_text("persisted", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"

    create_backup(settings, archive)
    with sqlite3.connect(settings.db_path) as connection:
        connection.execute("DELETE FROM users")
        connection.commit()
    (settings.uploads_dir / "note.txt").unlink()
    engine.dispose()

    restore_backup(settings, archive)
    with sqlite3.connect(settings.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert (settings.uploads_dir / "note.txt").read_text(encoding="utf-8") == "persisted"


def test_backup_excludes_secrets_models_and_environment_files(tmp_path):
    settings = Settings(
        _env_file=None,
        BASE_DIR=tmp_path,
        DATA_DIR=tmp_path / "data",
        MODELS_DIR=tmp_path / "models",
        DB_PATH=tmp_path / "data" / "aura.db",
        ENVIRONMENT="test",
    )
    settings.init_dirs()
    engine = create_engine(settings.resolved_database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    (settings.models_dir / "private.gguf").write_bytes(b"not-for-backup")
    (settings.data_dir / ".env").write_text("AUTH_SECRET_KEY=secret", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    create_backup(settings, archive)
    with tarfile.open(archive, "r:gz") as source:
        names = source.getnames()
    assert all(".env" not in name for name in names)
    assert all("private.gguf" not in name for name in names)
    assert all("models" not in name for name in names)


@pytest.mark.parametrize("kind", ["traversal", "symlink", "hardlink"])
def test_restore_rejects_unsafe_archive_members(tmp_path, kind):
    archive = tmp_path / f"unsafe-{kind}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("../outside")
        if kind == "symlink":
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        elif kind == "hardlink":
            member = tarfile.TarInfo("link")
            member.type = tarfile.LNKTYPE
            member.linkname = "aura.db"
        output.addfile(member)
    settings = Settings(_env_file=None, BASE_DIR=tmp_path, DATA_DIR=tmp_path / "data", ENVIRONMENT="test")
    with pytest.raises(RuntimeError):
        restore_backup(settings, archive)
