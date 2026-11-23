"""PT-31: R2-compatible immutable object contract, no real R2 transport.

The only implementation in this repo is the in-memory test store.
A future PRIVATE Cloudflare adapter must implement S3 PutObject with atomic
If-None-Match: *, read-your-write, and never silently overwrite on conflict.
No credentials, SDK, URL, HTTP requests or background jobs are included.
"""
from __future__ import annotations

from typing import Protocol

from r2_backup_contract import BackupObject, VerifiedBackup, verify_backup


class ConditionalObjectStore(Protocol):
    def put_if_absent(self, key: str, data: bytes) -> bool:
        """Atomic create-only write; False means key already exists."""
        ...

    def read(self, key: str) -> bytes:
        """Retrieve bytes from exactly this private key; no redirects."""
        ...


class InMemoryTestObjectStore:
    """Test-double ONLY, never persistent or connected to Cloudflare."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put_if_absent(self, key: str, data: bytes) -> bool:
        if key in self._objects:
            return False
        self._objects[key] = bytes(data)
        return True

    def read(self, key: str) -> bytes:
        return self._objects[key]


def store_backup(store: ConditionalObjectStore, backup: BackupObject) -> bool:
    """Verify first; store immutable bytes at the content-addressed key.

    Returns True if newly saved, False for identical prior copy. A conflict
    with differing bytes is fatal. This is a contract ONLY: connecting an
    actual R2 backend requires independent, explicit user authorization.
    """
    if type(backup) is not BackupObject:
        raise ValueError("PT31_INVALID_BACKUP_OBJECT")
    proof = verify_backup(backup.data, expected_account=backup.verified.account_id)
    if backup.key != proof.key or backup.verified != proof:
        raise ValueError("PT31_BACKUP_KEY_MISMATCH")
    result = store.put_if_absent(proof.key, backup.data)
    if type(result) is not bool:
        raise ValueError("PT31_INVALID_CONDITIONAL_RESULT")
    if not result:
        prior = store.read(proof.key)
        if type(prior) is not bytes or prior != backup.data:
            raise ValueError("PT31_IMMUTABLE_OBJECT_CONFLICT")
    return result


def inspect_stored_backup(
    store: ConditionalObjectStore, key: str, *,
    expected_account: str,
) -> VerifiedBackup:
    """Fail closed on wrong key, missing object, corrupt bytes or foreign account."""
    if type(key) is not str or len(key) > 256 or ".." in key:
        raise ValueError("PT31_OBJECT_KEY_BLOCKED")
    data = store.read(key)
    proof = verify_backup(data, expected_account=expected_account)
    if proof.key != key:
        raise ValueError("PT31_OBJECT_KEY_MISMATCH")
    return proof
