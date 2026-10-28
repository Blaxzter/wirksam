"""``app.scripts.setup_bucket``: the bucket's CORS rule for signed links."""

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.storage import PostgresStorage, S3Storage
from app.scripts import setup_bucket
from tests.fixtures.storage import storage_in_use


async def test_sets_the_cors_rule(
    moto_storage: S3Storage, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the bucket allows GET from any origin afterwards."""
    with storage_in_use(moto_storage):
        await setup_bucket.main()

    rules = moto_storage.client.get_bucket_cors(Bucket=moto_storage.bucket)["CORSRules"]
    assert rules[0].get("AllowedOrigins") == ["*"]
    assert rules[0].get("AllowedMethods") == ["GET", "HEAD"]
    assert "lets browsers read" in capsys.readouterr().out


async def test_a_key_without_the_right_only_warns(
    moto_storage: S3Storage, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test a refused PutBucketCors is reported, not raised: deploys go on."""
    denied = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutBucketCors"
    )
    with (
        storage_in_use(moto_storage),
        patch.object(moto_storage.client, "put_bucket_cors", side_effect=denied),
    ):
        await setup_bucket.main()

    assert "AccessDenied" in capsys.readouterr().out


async def test_nothing_to_do_on_postgres(capsys: pytest.CaptureFixture[str]) -> None:
    """Test the Postgres backend has no bucket to set up."""
    with storage_in_use(PostgresStorage()):
        await setup_bucket.main()

    assert "no bucket" in capsys.readouterr().out


async def test_an_unreachable_store_only_warns(
    moto_storage: S3Storage, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test a store that cannot be reached does not fail the deploy either."""
    down = EndpointConnectionError(endpoint_url="http://garage:3900")
    with (
        storage_in_use(moto_storage),
        patch.object(moto_storage.client, "put_bucket_cors", side_effect=down),
    ):
        await setup_bucket.main()

    assert "EndpointConnectionError" in capsys.readouterr().out
