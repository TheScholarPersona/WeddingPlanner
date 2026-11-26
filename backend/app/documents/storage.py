"""Object storage for document files.

Files are stored under keys that contain the organization and wedding, but access is never
decided by the key: every download goes through the API, which checks the user's rights under
row-level security first. The bucket is private; there are no public or presigned URLs.
"""

import asyncio
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

# Files stored with STORAGE_BACKEND=memory (tests).
MEMORY: dict[str, bytes] = {}


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class MemoryStorage:
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        MEMORY[key] = data

    async def get(self, key: str) -> bytes:
        return MEMORY[key]

    async def delete(self, key: str) -> None:
        MEMORY.pop(key, None)


_BUCKET_EXISTS = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")


class S3Storage:
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.s3_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except ClientError as error:
                # Another process (a parallel CLI run, a second worker) created it first.
                if error.response.get("Error", {}).get("Code") not in _BUCKET_EXISTS:
                    raise
        self._bucket_ready = True

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def _get(self, key: str) -> bytes:
        body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        try:
            return bytes(body.read())
        finally:
            body.close()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._put, key, data, content_type)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


@lru_cache
def _s3() -> S3Storage:
    return S3Storage()


def get_storage() -> Storage:
    if get_settings().storage_backend == "memory":
        return MemoryStorage()
    return _s3()
