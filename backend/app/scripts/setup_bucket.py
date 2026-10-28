"""Let browsers read signed links from the bucket (its CORS rule).

Run by ``scripts/prestart.sh`` on every deploy; with ``STORAGE_BACKEND=postgres``
it does nothing. Images are fetched by the frontend with ``fetch`` after the
API redirected it to a signed link, and a cross-origin ``fetch`` needs the
bucket's permission. See docs/STORAGE.md.

    python -m app.scripts.setup_bucket

A key that may not change bucket settings (an R2 token with object access
only), or a store that cannot be reached, is not an error: the script says
what to set by hand and exits 0, so a deploy does not stop over it.
"""

import asyncio

from botocore.exceptions import BotoCoreError, ClientError

from app.core.storage import S3Storage, get_storage


async def main() -> None:
    storage = get_storage()
    if not isinstance(storage, S3Storage):
        print("Files are stored in Postgres; no bucket to set up.")
        return
    try:
        await storage.allow_browser_reads()
    except (ClientError, BotoCoreError) as exc:
        code = (
            exc.response.get("Error", {}).get("Code", "unknown")
            if isinstance(exc, ClientError)
            else type(exc).__name__
        )
        print(
            f"Could not set the CORS rule on bucket {storage.bucket} ({code}). "
            "Set it by hand, as docs/STORAGE.md describes: plan images will "
            "not load until it is there."
        )
        return
    print(f"Bucket {storage.bucket} lets browsers read signed links.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point; main() is
    # covered by tests/scripts/test_setup_bucket.py
    asyncio.run(main())
