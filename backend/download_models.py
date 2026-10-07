"""Explicit, deterministic provisioning for optional local model artifacts."""

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings, config
from backend.app.runtime_diagnostics import (
    artifact_definition,
    embedding_status,
    llm_status,
    verify_artifact,
)


def _llm_artifact(settings: Settings = config) -> dict[str, Any]:
    artifact = artifact_definition("phi-3-mini-4k-instruct-q4")
    if artifact is None:
        raise RuntimeError("The LLM artifact is missing from the model manifest.")
    if artifact["filename"] != settings.model_filename:
        raise RuntimeError(
            "MODEL_FILENAME does not match the canonical manifest filename. "
            "Update the manifest or use its canonical filename."
        )
    return artifact


def _report_progress(downloaded: int, total: int | None) -> None:
    if total:
        percent = downloaded * 100 / total
        print(f"\rDownloading: {percent:6.2f}% ({downloaded / 1024**2:.1f} MiB)", end="", flush=True)
    else:
        print(f"\rDownloaded: {downloaded / 1024**2:.1f} MiB", end="", flush=True)


def download_file(
    url: str,
    destination: Path,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Stream one artifact to a .part file and atomically finalize it."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(destination.name + ".part")
    if part_path.exists():
        part_path.unlink()

    downloaded = 0
    try:
        request = Request(url, headers={"User-Agent": "AURA-provisioner/1.0"})
        with opener(request, timeout=30) as response, part_path.open("wb") as output:
            status = getattr(response, "status", 200)
            if status and status >= 400:
                raise RuntimeError(f"Model download failed with HTTP status {status}")
            header_size = response.headers.get("Content-Length")
            total = int(header_size) if header_size and header_size.isdigit() else expected_size
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                _report_progress(downloaded, total)
        print()

        if expected_size is not None and downloaded != expected_size:
            raise RuntimeError(f"Downloaded size {downloaded} does not match expected size {expected_size}")

        verification = verify_artifact(
            part_path,
            {"expected_size_bytes": expected_size, "sha256": expected_sha256},
        )
        if expected_sha256 and not verification["checksum_verified"]:
            raise RuntimeError("Downloaded artifact SHA-256 does not match the manifest.")
        os.replace(part_path, destination)
        return verify_artifact(
            destination,
            {"expected_size_bytes": expected_size, "sha256": expected_sha256},
        )
    except (HTTPError, URLError) as exc:
        if part_path.exists():
            part_path.unlink()
        raise RuntimeError(f"Model download failed: {exc.reason}") from exc
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def provision_llm(settings: Settings = config) -> int:
    artifact = _llm_artifact(settings)
    destination = settings.model_path
    if destination.exists():
        verification = verify_artifact(destination, artifact)
        print(json.dumps({"artifact": artifact["logical_name"], **verification}, indent=2))
        return 0 if verification["valid"] else 2
    try:
        verification = download_file(
            artifact["source"],
            destination,
            expected_size=artifact.get("expected_size_bytes"),
            expected_sha256=artifact.get("sha256"),
        )
        print(json.dumps({"artifact": artifact["logical_name"], **verification}, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - convert provisioning failures to CLI status
        print(f"LLM provisioning failed: {exc}", file=sys.stderr)
        return 1


def provision_embedding(settings: Settings = config) -> int:
    destination = settings.embedding_model_path
    if destination.exists():
        print(json.dumps(embedding_status(), indent=2))
        return 0
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("Embedding provisioning requires sentence-transformers.", file=sys.stderr)
        return 1

    temporary_parent = destination.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f"{destination.name}.", dir=temporary_parent))
    try:
        model = SentenceTransformer(
            settings.embedding_model,
            cache_folder=str(settings.embedding_cache_dir),
            device="cpu",
        )
        model.save(str(temporary_dir))
        os.replace(temporary_dir, destination)
        print(json.dumps(embedding_status(), indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - convert provisioning failures to CLI status
        print(f"Embedding provisioning failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)


def status(settings: Settings = config) -> dict[str, Any]:
    return {
        "llm": llm_status(),
        "embedding": embedding_status(),
        "paths": {
            "model_configured": bool(settings.model_filename),
            "embedding_configured": bool(settings.embedding_model),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision or inspect AURA local model artifacts.")
    parser.add_argument("--status", action="store_true", help="Show safe provisioning status and exit.")
    parser.add_argument("--verify", action="store_true", help="Verify the existing LLM artifact and exit.")
    parser.add_argument("--embedding", action="store_true", help="Explicitly provision the embedding model.")
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(status(), indent=2))
        return 0
    if args.verify:
        artifact = _llm_artifact()
        result = verify_artifact(config.model_path, artifact)
        print(json.dumps({"artifact": artifact["logical_name"], **result}, indent=2))
        return 0 if result["valid"] else 2
    if args.embedding:
        return provision_embedding()
    return provision_llm()


if __name__ == "__main__":
    raise SystemExit(main())
