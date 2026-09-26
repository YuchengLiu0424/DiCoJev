"""Safe image validation and provider-neutral native transport helpers."""

from __future__ import annotations

import base64
import binascii
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_to_bytes, urlparse

from .schemas import ImageRef

MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class NativeImage:
    url: str
    media_type: str
    size_bytes: int | None


def _validate_media_type(media_type: str) -> str:
    normalized = media_type.casefold().split(";", 1)[0].strip()
    if normalized not in SUPPORTED_MEDIA_TYPES:
        raise ValueError(f"unsupported image media type: {media_type}")
    return normalized


def _validate_bytes(data: bytes, media_type: str) -> None:
    if not data:
        raise ValueError("image bytes are empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds the 10 MiB limit")
    signatures = {
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/gif": (b"GIF87a", b"GIF89a"),
        "image/webp": (b"RIFF",),
    }
    if not any(data.startswith(signature) for signature in signatures[media_type]):
        raise ValueError(f"image bytes do not match {media_type}")
    if media_type == "image/webp" and data[8:12] != b"WEBP":
        raise ValueError("image bytes do not match image/webp")


def _data_url(data: bytes, media_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _parse_data_url(uri: str) -> tuple[bytes, str]:
    header, separator, payload = uri.partition(",")
    if not separator or not header.startswith("data:image/"):
        raise ValueError("invalid image data URL")
    media_type = _validate_media_type(header[5:].split(";", 1)[0])
    if len(payload) > (MAX_IMAGE_BYTES * 4 // 3) + 8:
        raise ValueError("image exceeds the 10 MiB limit")
    try:
        data = (
            base64.b64decode(payload, validate=True)
            if ";base64" in header
            else unquote_to_bytes(payload)
        )
    except (ValueError, binascii.Error) as error:
        raise ValueError("invalid image data URL payload") from error
    _validate_bytes(data, media_type)
    return data, media_type


def materialize_image(image: ImageRef) -> NativeImage:
    """Return provider-ready image input without exposing bytes to telemetry."""
    if image.data is not None:
        media_type = _validate_media_type(image.media_type or "")
        _validate_bytes(image.data, media_type)
        return NativeImage(_data_url(image.data, media_type), media_type, len(image.data))

    uri = image.uri or ""
    if uri.startswith("data:"):
        data, media_type = _parse_data_url(uri)
        if image.media_type is not None and _validate_media_type(image.media_type) != media_type:
            raise ValueError("declared media type does not match data URL")
        return NativeImage(uri, media_type, len(data))

    if "://" not in uri:
        return _materialize_path(Path(uri), image.media_type)

    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        media_type = _validate_media_type(image.media_type or _guess_media_type(parsed.path))
        return NativeImage(uri, media_type, None)

    path = Path(parsed.path).expanduser()
    return _materialize_path(path, image.media_type)


def _materialize_path(path: Path, declared_media_type: str | None) -> NativeImage:
    path = path.expanduser()
    if not path.is_file():
        raise ValueError(f"image path does not exist: {path}")
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds the 10 MiB limit")
    media_type = _validate_media_type(declared_media_type or _guess_media_type(path.name))
    data = path.read_bytes()
    _validate_bytes(data, media_type)
    return NativeImage(_data_url(data, media_type), media_type, size)


def _guess_media_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    if guessed is None:
        raise ValueError("image media type is required for an unknown extension")
    return guessed

