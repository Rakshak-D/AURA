# A1 Baseline Evidence

| Field | Value |
|---|---|
| Collected | 2026-11-16 |
| Branch | `feat/a1-model-providers` |
| Baseline / current source SHA | `9e98b50387c9149fb2bbe59380fc6c4618d6c065` |
| Expected A1 base | `9e98b50387c9149fb2bbe59380fc6c4618d6c065` |
| Initial worktree | Clean before evidence files were created |

## Repository preflight

- `origin/main` resolved to the expected A1 base SHA.
- The feature branch was created from that exact commit; `git merge-base HEAD origin/main` matched it.
- A0 source and CI configuration were present on the base.
- No A1 branch existed before this branch was created; no other worktree was registered.
- No application source was changed for this baseline.

## Baseline test results

Commands were run against the verified base before adding A1 code.

| Environment | Exact command | Result |
|---|---|---|
| Python 3.11.7 | `python -m pytest --collect-only -q` | 104 tests collected. |
| Python 3.11.7 | `AURA_ENVIRONMENT=test python -m pytest -m "not browser" -q` | 97 passed, 7 deselected, 3 warnings in 18.08s. |
| Python 3.12.10 | `AURA_ENVIRONMENT=test python -m pytest -m "not browser" -q` | 97 passed, 7 deselected, 4 warnings in 19.20s. |
| Python 3.11.7 | `AURA_RUN_BROWSER=1 python -m pytest -m browser -q` | 7 passed, 97 deselected, 3 warnings in 46.04s. |
| Python 3.11.7 | `python -m pytest -q tests/test_foundation.py::test_startup_does_not_initialize_model_or_chroma` | 1 passed, 3 warnings in 1.33s. |

The browser suite uses a fail-closed external-host guard; this run recorded no external browser requests. Warnings were existing dependency/runtime warnings, not test failures.

## Runtime observations

- Constructing the existing LLM singleton and starting the application did not load an LLM, embeddings model, or Chroma collection. The targeted startup test passed.
- No provider model was selected by the implementation engineer; no generation interaction was run.
- As part of read-only local inventory, invoking `ollama list` started the installed Ollama daemon. It listed already installed model entries; no model was downloaded, selected, or run. The daemon was left running because stopping a pre-existing local service would alter user state. No machine-specific model identifiers are included in this evidence.
- No cloud provider request or credential-bearing request was made.

## Baseline limits

These results describe A0 before A1 changes. They do not verify any new provider, credential storage, capability probe, Local only enforcement, or A1 Settings UI. The required real Ollama acceptance test remains pending an explicit owner-selected installed model.
