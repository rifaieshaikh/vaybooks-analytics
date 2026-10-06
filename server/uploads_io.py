"""Read upload bodies in chunks so a large Excel file cannot exceed the size cap."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from server.settings import MAX_UPLOAD_BYTES


async def read_upload_limited(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read an UploadFile in chunks; abort if over max_bytes. Returns full bytes for parsers."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, "File too large")
        chunks.append(chunk)
    return b"".join(chunks)
