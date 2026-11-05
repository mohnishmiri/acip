"""Export file sources: Azure Blob Storage (production) and local filesystem (demo/dev).

Both expose the same small interface so the ingestion pipeline is identical regardless of
where files come from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class BlobInfo:
    path: str  # path relative to the container
    size: int
    last_modified: datetime | None
    etag: str | None


class ExportSource(Protocol):
    kind: str

    def list_files(self, container: str, prefix: str) -> list[BlobInfo]: ...

    def download_to(self, container: str, path: str, fh: BinaryIO) -> None: ...

    def read_bytes(self, container: str, path: str) -> bytes: ...

    def check_access(self, container: str, prefix: str) -> tuple[bool, str]: ...


class LocalExportSource:
    kind = "local"

    def __init__(self, root: str):
        self.root = Path(root)

    def _base(self, container: str) -> Path:
        base = (self.root / container).resolve()
        if not str(base).startswith(str(self.root.resolve())):
            raise ValueError("container escapes export root")
        return base

    def list_files(self, container: str, prefix: str) -> list[BlobInfo]:
        base = self._base(container)
        start = (base / prefix).resolve()
        if not str(start).startswith(str(base)) or not start.exists():
            return []
        out: list[BlobInfo] = []
        for dirpath, _dirs, files in os.walk(start):
            for name in files:
                full = Path(dirpath) / name
                st = full.stat()
                out.append(
                    BlobInfo(
                        path=str(full.relative_to(base)).replace(os.sep, "/"),
                        size=st.st_size,
                        last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                        etag=f"{st.st_mtime_ns}-{st.st_size}",
                    )
                )
        return sorted(out, key=lambda b: b.path)

    def download_to(self, container: str, path: str, fh: BinaryIO) -> None:
        full = (self._base(container) / path).resolve()
        with open(full, "rb") as src:
            while chunk := src.read(1024 * 1024):
                fh.write(chunk)

    def read_bytes(self, container: str, path: str) -> bytes:
        return (self._base(container) / path).resolve().read_bytes()

    def check_access(self, container: str, prefix: str) -> tuple[bool, str]:
        base = self._base(container)
        if not base.exists():
            return False, f"Local export directory {base} does not exist"
        n = len(self.list_files(container, prefix))
        return True, f"Local export directory readable ({n} file(s) under '{prefix}')"


class AzureBlobExportSource:
    """Reads Cost Management export output. Requires 'Storage Blob Data Reader' for the
    collection identity on the storage account or container."""

    kind = "azure_blob"

    def __init__(self, account_url: str, credential=None):
        from azure.storage.blob import BlobServiceClient

        if credential is None:
            from app.integrations.azure_auth.credentials import get_credential

            credential = get_credential()
        self.account_url = account_url
        self.client = BlobServiceClient(account_url=account_url, credential=credential)

    def list_files(self, container: str, prefix: str) -> list[BlobInfo]:
        cc = self.client.get_container_client(container)
        return [
            BlobInfo(path=b.name, size=b.size or 0, last_modified=b.last_modified, etag=b.etag)
            for b in cc.list_blobs(name_starts_with=prefix)
        ]

    def download_to(self, container: str, path: str, fh: BinaryIO) -> None:
        self.client.get_blob_client(container, path).download_blob(max_concurrency=4).readinto(fh)

    def read_bytes(self, container: str, path: str) -> bytes:
        return self.client.get_blob_client(container, path).download_blob().readall()

    def check_access(self, container: str, prefix: str) -> tuple[bool, str]:
        cc = self.client.get_container_client(container)
        pages = cc.list_blobs(name_starts_with=prefix, results_per_page=5).by_page()
        first = next(pages, [])
        names = [b.name for b in first]
        return True, f"Listed container '{container}' prefix '{prefix}': {len(names)} blob(s) on first page"


def get_export_source(account_url: str | None = None, *, kind: str | None = None) -> ExportSource:
    settings = get_settings()
    if account_url and account_url.startswith("local://"):
        kind = "local"  # demo / file-drop export definitions always read the local directory
    kind = kind or settings.effective_export_source
    if kind == "azure_blob":
        url = account_url or settings.azure_storage_account_url
        if not url:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL is not configured")
        return AzureBlobExportSource(url)
    return LocalExportSource(settings.local_export_root)
