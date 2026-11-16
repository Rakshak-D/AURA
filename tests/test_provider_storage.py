from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    REQUIRED_SCHEMA_VERSION,
    Base,
    _apply_schema_migrations,
    schema_status,
    utc_now,
)
from backend.app.models.sql_models import (
    ChatHistory,
    Document,
    ModelRoleSelection,
    ProviderCapabilityCache,
    ProviderConnection,
    ProviderCredential,
    Reminder,
    RoutineEvent,
    Task,
    User,
    UserModelPreference,
)
from backend.app.models.pydantic_models import ModelRoleSelectionValue


def _create_v4_engine(path):
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        alice = User(name="Alice", settings={"legacy_model": "gguf/old-model"})
        bob = User(name="Bob")
        session.add_all([alice, bob])
        session.flush()
        task = Task(title="preserved task", user_id=alice.id)
        session.add(task)
        session.flush()
        session.add_all(
            [
                Reminder(
                    user_id=alice.id,
                    task_id=task.id,
                    reminder_time=utc_now() + timedelta(hours=1),
                ),
                ChatHistory(
                    user_id=alice.id,
                    role="user",
                    content="preserved chat",
                ),
                Document(
                    user_id=alice.id,
                    filename="legacy.txt",
                    content="preserved document",
                    file_type="text/plain",
                    indexing_state="indexed",
                ),
                RoutineEvent(
                    user_id=bob.id,
                    title="preserved routine",
                    event_type="work",
                    start_time="09:00",
                    duration_minutes=60,
                    days_of_week="0,1,2,3,4",
                ),
            ]
        )
        session.commit()
        user_ids = (alice.id, bob.id)

    with engine.begin() as connection:
        for table in (
            "provider_credentials",
            "model_role_selections",
            "provider_capability_cache",
            "user_model_preferences",
            "provider_connections",
        ):
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
        if "embedding_model_id" in {
            column["name"] for column in inspect(connection).get_columns("documents")
        }:
            connection.exec_driver_sql(
                "ALTER TABLE documents DROP COLUMN embedding_model_id"
            )
        connection.exec_driver_sql(
            "CREATE TABLE schema_version (version INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO schema_version(version) VALUES (4)")

    return engine, factory, user_ids


def _create_previous_a1a_v5_engine(path):
    """Create the prior A1-A schema without the R1 provenance columns."""
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            table
            for table in Base.metadata.sorted_tables
            if table.name != "provider_capability_cache"
        ],
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        user = User(name="Previous A1-A user")
        session.add(user)
        session.flush()
        connection = ProviderConnection(
            id="previous-a1a-connection",
            user_id=user.id,
            name="Existing connection",
            provider_type="openai_compatible",
            base_url="https://example.invalid/v1",
        )
        session.add_all(
            [
                connection,
                UserModelPreference(user_id=user.id, local_only=False),
                ModelRoleSelection(
                    user_id=user.id,
                    role="chat",
                    connection_id=connection.id,
                    model_id="existing-model",
                ),
            ]
        )
        session.commit()
        user_id = user.id

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_version (version INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO schema_version(version) VALUES (5)")
        connection.exec_driver_sql(
            """CREATE TABLE provider_capability_cache (
                user_id INTEGER NOT NULL,
                connection_id VARCHAR(64) NOT NULL,
                config_revision INTEGER NOT NULL CHECK (config_revision >= 0),
                model_id VARCHAR(512) NOT NULL,
                context_length INTEGER CHECK (context_length IS NULL OR context_length > 0),
                tools VARCHAR(16) NOT NULL DEFAULT 'unknown'
                    CHECK (tools IN ('supported', 'unsupported', 'unknown')),
                json_mode VARCHAR(16) NOT NULL DEFAULT 'unknown'
                    CHECK (json_mode IN ('supported', 'unsupported', 'unknown')),
                vision VARCHAR(16) NOT NULL DEFAULT 'unknown'
                    CHECK (vision IN ('supported', 'unsupported', 'unknown')),
                streaming VARCHAR(16) NOT NULL DEFAULT 'unknown'
                    CHECK (streaming IN ('supported', 'unsupported', 'unknown')),
                embeddings VARCHAR(16) NOT NULL DEFAULT 'unknown'
                    CHECK (embeddings IN ('supported', 'unsupported', 'unknown')),
                checked_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, connection_id, config_revision, model_id),
                FOREIGN KEY (user_id, connection_id)
                    REFERENCES provider_connections (user_id, id) ON DELETE CASCADE
            )"""
        )
        connection.exec_driver_sql(
            """INSERT INTO provider_capability_cache
               (user_id, connection_id, config_revision, model_id, context_length,
                tools, json_mode, vision, streaming, embeddings, checked_at)
               VALUES (?, ?, 0, ?, 4096, 'supported', 'unsupported', 'unknown',
                       'supported', 'unknown', CURRENT_TIMESTAMP)""",
            (user_id, "previous-a1a-connection", "existing-model"),
        )

    return engine, factory, user_id


@pytest.fixture
def provider_db(tmp_path):
    engine, factory, user_ids = _create_v4_engine(tmp_path / "provider-v4.db")
    _apply_schema_migrations(engine)
    with factory() as session:
        yield session, user_ids
    engine.dispose()


def test_v4_migration_preserves_data_and_creates_no_role_assignments(tmp_path):
    engine, factory, user_ids = _create_v4_engine(tmp_path / "migration-v4.db")

    _apply_schema_migrations(engine)

    with factory() as session:
        assert session.execute(text("SELECT version FROM schema_version")).scalar() == 6
        assert session.query(User).count() == 2
        assert session.query(Task).filter_by(title="preserved task").count() == 1
        assert session.query(Reminder).count() == 1
        assert session.query(ChatHistory).filter_by(content="preserved chat").count() == 1
        document = session.query(Document).filter_by(filename="legacy.txt").one()
        assert document.content == "preserved document"
        assert document.indexing_state == "indexed"
        assert document.embedding_model_id is None
        assert session.query(RoutineEvent).filter_by(title="preserved routine").count() == 1
        assert session.query(ModelRoleSelection).count() == 0
        assert session.query(ProviderConnection).count() == 0
        assert session.query(UserModelPreference).count() == 2
        assert all(
            preference.local_only is True
            for preference in session.query(UserModelPreference).all()
        )
        assert session.get(User, user_ids[0]).settings == {
            "legacy_model": "gguf/old-model"
        }

    assert schema_status(engine) == {"ready": True, "version": 6, "missing": []}
    _apply_schema_migrations(engine)
    assert schema_status(engine)["ready"] is True
    engine.dispose()


def test_previous_a1a_v5_migration_preserves_cache_and_assignments(tmp_path):
    engine, factory, user_id = _create_previous_a1a_v5_engine(
        tmp_path / "previous-a1a-v5.db"
    )

    _apply_schema_migrations(engine)

    with factory() as session:
        assert session.execute(text("SELECT version FROM schema_version")).scalar() == 6
        cache = ProviderConnection.get_owned(
            session, user_id, "previous-a1a-connection"
        ).current_capability_cache(session, "existing-model")
        assert cache is not None
        assert cache.tools == "supported"
        assert cache.json_mode == "unsupported"
        assert cache.context_length == 4096
        assert cache.tools_source == "unknown"
        assert cache.json_mode_source == "unknown"
        assert cache.context_length_source == "unknown"
        assert cache.vision_source == "unknown"
        assert cache.streaming_source == "unknown"
        assert cache.embeddings_source == "unknown"
        role = ModelRoleSelection.get_for_user(session, user_id, "chat")
        assert role is not None
        assert role.connection_id == "previous-a1a-connection"
        assert role.model_id == "existing-model"
        assert UserModelPreference.get_or_default(session, user_id).local_only is False
        cache.tools_source = "raw provider diagnostics"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert (
            ProviderConnection.get_owned(
                session, user_id, "previous-a1a-connection"
            )
            .current_capability_cache(session, "existing-model")
            .tools_source
            == "unknown"
        )

    assert schema_status(engine) == {"ready": True, "version": 6, "missing": []}
    engine.dispose()


def test_fresh_schema_bootstrap_creates_default_preference(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        user = User(name="Fresh user")
        session.add(user)
        session.commit()
        user_id = user.id
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_version (version INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO schema_version(version) VALUES (0)")

    _apply_schema_migrations(engine)

    with factory() as session:
        assert session.get(UserModelPreference, user_id).local_only is True
        assert session.query(ModelRoleSelection).count() == 0
    assert schema_status(engine) == {"ready": True, "version": 6, "missing": []}
    engine.dispose()


def test_connection_names_are_user_scoped_and_application_lookup_is_owned(provider_db):
    session, (alice_id, bob_id) = provider_db
    first = ProviderConnection(
        id="alice-openai-primary",
        user_id=alice_id,
        name="Primary",
        provider_type="openai_compatible",
        base_url="https://primary.example/v1",
    )
    second = ProviderConnection(
        id="alice-openai-secondary",
        user_id=alice_id,
        name="Secondary",
        provider_type="openai_compatible",
        base_url="https://secondary.example/v1",
    )
    same_name_other_user = ProviderConnection(
        id="bob-openai-primary",
        user_id=bob_id,
        name="Primary",
        provider_type="openai_compatible",
        base_url="https://bob.example/v1",
    )
    session.add_all([first, second, same_name_other_user])
    session.commit()

    assert ProviderConnection.get_owned(session, alice_id, first.id) is first
    assert ProviderConnection.get_owned(session, bob_id, first.id) is None
    assert first.provider_type == second.provider_type
    assert first.id != second.id

    session.add(
        ProviderConnection(
            id="alice-openai-duplicate-name",
            user_id=alice_id,
            name="Primary",
            provider_type="openai_compatible",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_role_foreign_key_rejects_cross_user_assignment_and_lookup_is_scoped(
    provider_db,
):
    session, (alice_id, bob_id) = provider_db
    connection = ProviderConnection(
        id="alice-ollama",
        user_id=alice_id,
        name="Local Ollama",
        provider_type="ollama",
        base_url="http://127.0.0.1:11434",
    )
    session.add(connection)
    session.flush()
    role = ModelRoleSelection(
        user_id=alice_id,
        role="chat",
        connection_id=connection.id,
        model_id="explicit-model-id",
    )
    validated_role = ModelRoleSelectionValue(
        role="chat",
        connection_id=connection.id,
        model_id="explicit-model-id",
    )
    assert validated_role.connection_id == connection.id
    assert validated_role.model_id == "explicit-model-id"
    with pytest.raises(ValidationError):
        ModelRoleSelectionValue(
            role="unknown-role",
            connection_id=connection.id,
            model_id="explicit-model-id",
        )
    with pytest.raises(ValidationError):
        ModelRoleSelectionValue(
            role="chat",
            connection_id=" ",
            model_id="explicit-model-id",
        )
    session.add(role)
    session.commit()

    assert ModelRoleSelection.get_for_user(session, alice_id, "chat") is role
    assert ModelRoleSelection.get_for_user(session, bob_id, "chat") is None

    session.add(
        ModelRoleSelection(
            user_id=bob_id,
            role="chat",
            connection_id=connection.id,
            model_id="cross-user-model",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert session.query(ModelRoleSelection).count() == 1


def test_soft_removal_preserves_exact_role_reference_and_marks_it_unavailable(
    provider_db,
):
    session, (alice_id, _) = provider_db
    connection = ProviderConnection(
        id="alice-chat",
        user_id=alice_id,
        name="Chat",
        provider_type="openai_compatible",
        base_url="https://chat.example/v1",
    )
    session.add(connection)
    session.flush()
    selection = ModelRoleSelection(
        user_id=alice_id,
        role="chat",
        connection_id=connection.id,
        model_id="provider/model-v1",
    )
    session.add(selection)
    credential = ProviderCredential(
        credential_id="to-remove",
        user_id=alice_id,
        connection_id=connection.id,
        format_version=1,
        key_id="os-key-id",
        nonce=b"n" * 12,
        ciphertext=b"c" * 16,
    )
    session.add(credential)
    session.commit()

    connection.base_url = "https://updated.example/v1"
    connection.advance_config_revision()
    connection.mark_removed(session)
    session.commit()
    session.expire_all()

    stored_role = ModelRoleSelection.get_for_user(session, alice_id, "chat")
    assert stored_role is not None
    assert stored_role.connection_id == "alice-chat"
    assert stored_role.model_id == "provider/model-v1"
    assert stored_role.is_available is False
    assert ProviderConnection.get_owned(session, alice_id, "alice-chat").deleted_at is not None
    assert ProviderCredential.get_owned(session, alice_id, "alice-chat") is None


def test_capability_cache_is_scoped_by_user_connection_revision_and_model(provider_db):
    session, (alice_id, bob_id) = provider_db
    alice_one = ProviderConnection(
        id="alice-one",
        user_id=alice_id,
        name="One",
        provider_type="openai_compatible",
        base_url="https://one.example/v1",
    )
    alice_two = ProviderConnection(
        id="alice-two",
        user_id=alice_id,
        name="Two",
        provider_type="openai_compatible",
        base_url="https://two.example/v1",
    )
    bob_one = ProviderConnection(
        id="bob-one",
        user_id=bob_id,
        name="One",
        provider_type="openai_compatible",
        base_url="https://bob.example/v1",
    )
    session.add_all([alice_one, alice_two, bob_one])
    session.flush()

    cache_a = ProviderCapabilityCache(
        user_id=alice_id,
        connection_id=alice_one.id,
        config_revision=0,
        model_id="same-model-id",
        checked_at=utc_now(),
        tools="supported",
        tools_source="controlled_probe",
        json_mode="unsupported",
        json_mode_source="provider_metadata",
        context_length=8192,
        context_length_source="provider_metadata",
    )
    cache_other_model = ProviderCapabilityCache(
        user_id=alice_id,
        connection_id=alice_one.id,
        config_revision=0,
        model_id="other-model-id",
        checked_at=utc_now(),
        tools="supported",
    )
    cache_other_revision = ProviderCapabilityCache(
        user_id=alice_id,
        connection_id=alice_one.id,
        config_revision=7,
        model_id="same-model-id",
        checked_at=utc_now(),
        streaming="unsupported",
    )
    cache_other_connection = ProviderCapabilityCache(
        user_id=alice_id,
        connection_id=alice_two.id,
        config_revision=0,
        model_id="same-model-id",
        checked_at=utc_now(),
        vision="supported",
    )
    cache_other_user = ProviderCapabilityCache(
        user_id=bob_id,
        connection_id=bob_one.id,
        config_revision=0,
        model_id="same-model-id",
        checked_at=utc_now(),
        embeddings="unsupported",
    )
    session.add_all(
        [
            cache_a,
            cache_other_model,
            cache_other_revision,
            cache_other_connection,
            cache_other_user,
        ]
    )
    session.commit()

    session.expire(cache_a)
    assert cache_a.tools_source == "controlled_probe"
    assert cache_a.json_mode_source == "provider_metadata"
    assert cache_a.context_length_source == "provider_metadata"
    assert cache_a.vision_source == "unknown"
    assert cache_a.streaming_source == "unknown"
    assert cache_a.embeddings_source == "unknown"

    assert alice_one.current_capability_cache(session, "same-model-id") is cache_a
    assert alice_two.current_capability_cache(session, "same-model-id") is cache_other_connection
    assert bob_one.current_capability_cache(session, "same-model-id") is cache_other_user
    assert alice_one.current_capability_cache(session, "other-model-id") is cache_other_model

    alice_one.advance_config_revision()
    session.commit()
    assert alice_one.current_capability_cache(session, "same-model-id") is None
    assert alice_two.current_capability_cache(session, "same-model-id") is cache_other_connection
    assert bob_one.current_capability_cache(session, "same-model-id") is cache_other_user


def test_capability_cache_rejects_unbounded_or_unrecognized_provenance(provider_db):
    session, (alice_id, _bob_id) = provider_db
    connection = ProviderConnection(
        id="alice-provenance-check",
        user_id=alice_id,
        name="Provenance check",
        provider_type="openai_compatible",
    )
    session.add(connection)
    session.flush()
    cache = ProviderCapabilityCache(
        user_id=alice_id,
        connection_id=connection.id,
        config_revision=0,
        model_id="model-a",
        checked_at=utc_now(),
        tools="supported",
        tools_source="raw provider response containing diagnostic text",
    )
    session.add(cache)

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert (
        session.query(ProviderCapabilityCache)
        .filter_by(user_id=alice_id, connection_id=connection.id)
        .count()
        == 0
    )


def test_credential_records_contain_only_ciphertext_and_are_owner_scoped(provider_db):
    session, (alice_id, bob_id) = provider_db
    connection = ProviderConnection(
        id="alice-secure",
        user_id=alice_id,
        name="Secure connection",
        provider_type="openai_compatible",
    )
    session.add(connection)
    session.flush()
    credential = ProviderCredential(
        credential_id="credential-a",
        user_id=alice_id,
        connection_id=connection.id,
        format_version=1,
        key_id="os-key-id",
        nonce=b"n" * 12,
        ciphertext=b"c" * 16,
    )
    session.add(credential)
    session.commit()

    columns = {column.name for column in ProviderCredential.__table__.columns}
    assert {"format_version", "key_id", "nonce", "ciphertext"}.issubset(columns)
    assert not {"plaintext", "api_key", "master_key"}.intersection(columns)
    assert ProviderCredential.get_owned(session, alice_id, connection.id) is credential
    assert ProviderCredential.get_owned(session, bob_id, connection.id) is None

    session.add(
        ProviderCredential(
            credential_id="cross-user-credential",
            user_id=bob_id,
            connection_id=connection.id,
            format_version=1,
            key_id="os-key-id",
            nonce=b"x" * 12,
            ciphertext=b"y" * 16,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_local_only_defaults_true_and_no_roles_are_implicitly_selected(provider_db):
    session, (alice_id, bob_id) = provider_db
    preference = UserModelPreference.get_or_default(session, alice_id)
    assert preference.local_only is True
    assert UserModelPreference.get_or_default(session, bob_id).local_only is True
    assert session.query(ModelRoleSelection).count() == 0

    new_user = User(name="New account")
    session.add(new_user)
    session.commit()
    assert UserModelPreference.get_or_default(session, new_user.id).local_only is True
    assert session.get(UserModelPreference, new_user.id) is None

    preference.local_only = False
    session.commit()
    assert UserModelPreference.get_or_default(session, alice_id).local_only is False
    assert UserModelPreference.get_or_default(session, bob_id).local_only is True


def test_schema_v6_requires_provider_tables_composite_ownership_and_embedding_identity(
    provider_db,
):
    session, _user_ids = provider_db
    engine = session.get_bind()
    assert schema_status(engine) == {"ready": True, "version": 6, "missing": []}
    tables = set(inspect(engine).get_table_names())
    assert {
        "provider_connections",
        "provider_credentials",
        "model_role_selections",
        "provider_capability_cache",
        "user_model_preferences",
    }.issubset(tables)
    capability_columns = {
        column["name"] for column in inspect(engine).get_columns("provider_capability_cache")
    }
    assert {
        "context_length_source",
        "tools_source",
        "json_mode_source",
        "vision_source",
        "streaming_source",
        "embeddings_source",
    }.issubset(capability_columns)
    assert "embedding_model_id" in {
        column["name"] for column in inspect(engine).get_columns("documents")
    }
    assert REQUIRED_SCHEMA_VERSION == 6
