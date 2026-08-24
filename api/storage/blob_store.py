"""Azure Blob Storage with local filesystem fallback (no Cosmos DB)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import BinaryIO

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings


class BlobStore:
    def __init__(self, backend: str, container: str, connection_string: str | None, local_root: str) -> None:
        self.backend = backend
        self.container = container
        self._local_root = Path(local_root)
        self._client = None
        if backend == "azure":
            if not connection_string:
                raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required for azure backend")
            self._client = BlobServiceClient.from_connection_string(
                connection_string,
                connection_timeout=300,
                read_timeout=600,
            )
            self._container_client = self._client.get_container_client(container)
            if not self._container_client.exists():
                self._container_client.create_container()

    def _local_path(self, key: str) -> Path:
        return self._local_root / self.container / key

    def write_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        if self.backend == "local":
            path = self._local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return key
        assert self._client is not None
        blob = self._container_client.get_blob_client(key)
        settings = ContentSettings(content_type=content_type) if content_type else None
        blob.upload_blob(data, overwrite=True, content_settings=settings, timeout=600)
        return key

    def write_json(self, key: str, payload: dict | list) -> str:
        return self.write_bytes(key, json.dumps(payload, indent=2).encode("utf-8"), "application/json")

    def read_bytes(self, key: str) -> bytes | None:
        if self.backend == "local":
            path = self._local_path(key)
            if not path.is_file():
                return None
            return path.read_bytes()
        assert self._client is not None
        blob = self._container_client.get_blob_client(key)
        try:
            return blob.download_blob().readall()
        except ResourceNotFoundError:
            return None

    def read_json(self, key: str) -> dict | list | None:
        raw = self.read_bytes(key)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))

    def exists(self, key: str) -> bool:
        if self.backend == "local":
            return self._local_path(key).is_file()
        assert self._client is not None
        blob = self._container_client.get_blob_client(key)
        try:
            blob.get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False

    def size_bytes(self, key: str) -> int | None:
        """Object size without downloading it (inference deploy pricing)."""
        if self.backend == "local":
            path = self._local_path(key)
            return path.stat().st_size if path.is_file() else None
        assert self._client is not None
        blob = self._container_client.get_blob_client(key)
        try:
            return int(blob.get_blob_properties().size)
        except ResourceNotFoundError:
            return None

    def delete(self, key: str) -> None:
        if self.backend == "local":
            path = self._local_path(key)
            if path.is_file():
                path.unlink()
            return
        assert self._client is not None
        blob = self._container_client.get_blob_client(key)
        try:
            blob.delete_blob()
        except ResourceNotFoundError:
            pass

    def upload_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> str:
        data = stream.read()
        return self.write_bytes(key, data, content_type)

    def get_connection_string(self) -> str | None:
        if self.backend != "azure":
            return None
        return os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AZURE_STORAGE_CONNECTION")

    def blob_url(self, key: str) -> str | None:
        """Public HTTPS URL for a blob (used as dataset reference)."""
        if self.backend != "azure" or not self._client:
            return None
        account = self._client.account_name
        return f"https://{account}.blob.core.windows.net/{self.container}/{key}"

    def list_prefix(self, prefix: str) -> list[str]:
        if self.backend == "local":
            base = self._local_root / self.container / prefix
            if not base.exists():
                return []
            return [
                str(p.relative_to(self._local_root / self.container)).replace("\\", "/")
                for p in base.rglob("*")
                if p.is_file()
            ]
        assert self._client is not None
        return [b.name for b in self._container_client.list_blobs(name_starts_with=prefix)]

    def copy_blob(self, source_key: str, dest_key: str) -> str:
        """Server-side or local copy of a single blob."""
        if self.backend == "local":
            src = self._local_path(source_key)
            dst = self._local_path(dest_key)
            if not src.is_file():
                raise FileNotFoundError(source_key)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            return dest_key
        assert self._client is not None
        src_blob = self._container_client.get_blob_client(source_key)
        dest_blob = self._container_client.get_blob_client(dest_key)
        dest_blob.start_copy_from_url(src_blob.url)
        return dest_key

    def copy_prefix(self, source_prefix: str, dest_prefix: str) -> int:
        """Copy all blobs under source_prefix to dest_prefix. Returns number copied."""
        src = source_prefix.rstrip("/") + "/"
        dst = dest_prefix.rstrip("/") + "/"
        keys = [k for k in self.list_prefix(src) if k.startswith(src)]
        if not keys:
            keys = [k for k in self.list_prefix(source_prefix.rstrip("/")) if k == source_prefix.rstrip("/")]
        copied = 0
        for key in keys:
            rel = key[len(src) :] if key.startswith(src) else key.split("/")[-1]
            self.copy_blob(key, f"{dst}{rel}")
            copied += 1
        return copied


def get_blob_store() -> BlobStore:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    container = os.getenv("AZURE_STORAGE_CONTAINER", "visiondock")
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AZURE_STORAGE_CONNECTION")
    local_root = os.getenv("LOCAL_STORAGE_PATH", os.path.join(os.path.dirname(__file__), "..", "data"))
    return BlobStore(backend=backend, container=container, connection_string=conn, local_root=local_root)
