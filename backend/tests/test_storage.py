"""S3 storage: creating the bucket tolerates a parallel process that created it first."""

from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.documents.storage import S3Storage


class FakeS3:
    def __init__(self, create_error: str | None) -> None:
        self.create_error = create_error
        self.objects: dict[str, bytes] = {}
        self.create_calls = 0

    def head_bucket(self, **_: Any) -> None:
        raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, **_: Any) -> None:
        self.create_calls += 1
        if self.create_error:
            raise ClientError({"Error": {"Code": self.create_error}}, "CreateBucket")

    def put_object(self, *, Key: str, Body: bytes, **_: Any) -> None:
        self.objects[Key] = Body


def _store(client: FakeS3) -> S3Storage:
    store = S3Storage.__new__(S3Storage)
    store._bucket = "test-bucket"
    store._client = client
    store._bucket_ready = False
    return store


@pytest.mark.parametrize("code", ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"])
async def test_put_succeeds_when_another_process_created_the_bucket(code: str) -> None:
    client = FakeS3(create_error=code)
    await _store(client).put("a/b.txt", b"hello", "text/plain")
    assert client.objects == {"a/b.txt": b"hello"}
    assert client.create_calls == 1


async def test_other_bucket_errors_are_raised() -> None:
    client = FakeS3(create_error="AccessDenied")
    with pytest.raises(ClientError):
        await _store(client).put("a/b.txt", b"hello", "text/plain")
    assert client.objects == {}
