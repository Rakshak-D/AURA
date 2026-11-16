# A1-A dependency verification

## Task B additions

| Package | Exact pin | Platform | Reported license | Purpose |
|---|---:|---|---|---|
| HTTPX | 0.28.1 | All supported Python platforms | BSD-3-Clause | Planned shared provider transport; not imported by Task A/B code |
| cryptography | 50.0.2 | All supported Python platforms | Apache-2.0 OR BSD-3-Clause | AES-256-GCM credential encryption |
| keyring | 25.7.0 | Windows only (`sys_platform == "win32"`) | MIT | Explicit Windows Credential Manager backend |
| pywin32-ctypes | 0.2.3 | Windows only (`sys_platform == "win32"`) | BSD-3-Clause | Windows Credential Manager API support without full pywin32 |

The four planned pins were retained after checking package metadata and successfully installing the complete `requirements-dev.txt` dependency set, including `requirements.txt`, in isolated Windows virtual environments using Python 3.11.7 and 3.12.10. Both installations completed, `pip check` reported no broken requirements, and the Task B credential tests passed in both environments. The Windows-specific `WinVaultKeyring` backend loaded with `CRED_PERSIST_LOCAL_MACHINE` in both environments. No actual Credential Manager entry was created or read during tests.

Measured installed footprint of the four distributions, summed from their installed distribution file sizes:

- Python 3.11.7: 11,135,780 bytes (HTTPX 401,543; cryptography 10,450,466; keyring 209,061; pywin32-ctypes 74,710).
- Python 3.12.10: 11,135,776 bytes (HTTPX 401,541; cryptography 10,450,466; keyring 209,059; pywin32-ctypes 74,710).

These are installed files for the four named distributions only; they exclude shared/transitive dependencies and are not a repository size delta. No model or GPU package was added. Package metadata was checked from the installed distributions; no license files were vendored or removed.

## Verification commands

The commands below were run from the repository root. `PY311` and `PY312` refer to isolated virtual environments under the system temporary directory, not repository paths.

```powershell
& $PY311 -m pytest tests/test_provider_secrets.py -q
& $PY312 -m pytest tests/test_provider_secrets.py -q
& $PY311 -m pip check
& $PY312 -m pip check
```

The focused credential module passed 9 tests in each environment. The expanded A0 security/authentication/database regression selection passed 68 tests in each environment; exact command and details are recorded in `SECURITY_REVIEW.md`.
