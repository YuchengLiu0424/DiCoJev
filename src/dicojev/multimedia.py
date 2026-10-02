"""Local attachment preprocessing for the text-and-image DiCoJev core."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import DecisionRequest, ImageRef

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".py",
    ".js",
    ".ts",
    ".log",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


@dataclass(frozen=True)
class AttachmentResult:
    text_blocks: tuple[str, ...] = ()
    images: tuple[ImageRef, ...] = ()
    metadata: tuple[dict[str, Any], ...] = ()


class LocalMediaIngestor:
    """Convert local files, speech, and video into bounded text/image state.

    Text and images use the base installation. PDF/DOCX and speech/video dependencies are lazy
    optional extras so importing DiCoJev never downloads a model or media stack.
    """

    def __init__(
        self,
        *,
        max_text_chars: int = 100_000,
        max_file_bytes: int = 10 * 1024 * 1024,
        max_media_bytes: int = 500 * 1024 * 1024,
        video_frames: int = 4,
        speech_model: str | None = None,
    ) -> None:
        self.max_text_chars = max_text_chars
        self.max_file_bytes = max_file_bytes
        self.max_media_bytes = max_media_bytes
        self.video_frames = video_frames
        self.speech_model = speech_model or os.getenv("DICOJEV_WHISPER_MODEL", "base")
        self._speech_runtime = None

    def ingest(self, paths: list[str] | tuple[str, ...]) -> AttachmentResult:
        text_blocks: list[str] = []
        images: list[ImageRef] = []
        metadata: list[dict[str, Any]] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"Attachment does not exist: {path}")
            suffix = path.suffix.lower()
            limit = (
                self.max_media_bytes
                if suffix in AUDIO_SUFFIXES | VIDEO_SUFFIXES
                else self.max_file_bytes
            )
            if path.stat().st_size > limit:
                raise ValueError(f"Attachment exceeds {limit // (1024 * 1024)} MiB: {path}")
            if suffix in TEXT_SUFFIXES:
                text = self._read_text(path)
                text_blocks.append(f"[File: {path.name}]\n{text}")
                metadata.append(self._metadata(path, "text"))
            elif suffix in IMAGE_SUFFIXES:
                images.append(self._read_image(path))
                metadata.append(self._metadata(path, "image"))
            elif suffix == ".pdf":
                text_blocks.append(f"[PDF: {path.name}]\n{self._read_pdf(path)}")
                metadata.append(self._metadata(path, "document"))
            elif suffix == ".docx":
                text_blocks.append(f"[Document: {path.name}]\n{self._read_docx(path)}")
                metadata.append(self._metadata(path, "document"))
            elif suffix in AUDIO_SUFFIXES:
                text_blocks.append(f"[Speech transcript: {path.name}]\n{self._transcribe(path)}")
                metadata.append(self._metadata(path, "audio"))
            elif suffix in VIDEO_SUFFIXES:
                video_images, transcript, detail = self._read_video(path)
                images.extend(video_images)
                if transcript:
                    text_blocks.append(f"[Video transcript: {path.name}]\n{transcript}")
                metadata.append({**self._metadata(path, "video"), **detail})
            else:
                raise ValueError(f"Unsupported attachment type: {path.suffix or '(none)'}")
        total = sum(len(block) for block in text_blocks)
        if total > self.max_text_chars:
            raise ValueError(
                f"Extracted attachment text exceeds {self.max_text_chars:,} characters"
            )
        return AttachmentResult(tuple(text_blocks), tuple(images), tuple(metadata))

    def enrich_request(
        self, request: DecisionRequest, paths: list[str] | tuple[str, ...]
    ) -> DecisionRequest:
        if not paths:
            return request
        result = self.ingest(paths)
        text_parts = [request.state.text, *result.text_blocks]
        text = "\n\n".join(part for part in text_parts if part)
        structured = dict(request.state.structured)
        structured["attachments"] = list(result.metadata)
        state = request.state.model_copy(
            update={
                "text": text,
                "images": (*request.state.images, *result.images),
                "structured": structured,
            }
        )
        return request.model_copy(update={"state": state})

    def _bounded_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def _read_text(self, path: Path) -> str:
        data = self._bounded_bytes(path)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

    def _read_image(self, path: Path) -> ImageRef:
        data = self._bounded_bytes(path)
        media_type = mimetypes.guess_type(path.name)[0] or "image/unknown"
        return ImageRef(data=data, media_type=media_type, alt_text=f"Attachment {path.name}")

    def _read_pdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError('PDF intake requires: pip install "dicojev[media]"') from error
        reader = PdfReader(path)
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:50]).strip()

    def _read_docx(self, path: Path) -> str:
        try:
            from docx import Document
        except ImportError as error:
            raise RuntimeError('DOCX intake requires: pip install "dicojev[media]"') from error
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    def _speech_model(self):
        if self._speech_runtime is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:
                raise RuntimeError(
                    'Speech intake requires: pip install "dicojev[media]"'
                ) from error
            self._speech_runtime = WhisperModel(
                self.speech_model, device="cpu", compute_type="int8"
            )
        return self._speech_runtime

    def _transcribe(self, path: Path) -> str:
        segments, _info = self._speech_model().transcribe(str(path), vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())

    def _read_video(self, path: Path) -> tuple[list[ImageRef], str, dict[str, Any]]:
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError('Video intake requires: pip install "dicojev[media]"') from error
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ValueError(f"Could not open video: {path}")
        try:
            frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            count = min(self.video_frames, frame_count)
            indexes = (
                [0]
                if count == 1
                else [round(index * (frame_count - 1) / (count - 1)) for index in range(count)]
            )
            frames: list[ImageRef] = []
            for frame_index in indexes:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    continue
                encoded, buffer = cv2.imencode(".jpg", frame)
                if encoded:
                    frames.append(
                        ImageRef(
                            data=buffer.tobytes(),
                            media_type="image/jpeg",
                            alt_text=f"{path.name} frame {frame_index}",
                        )
                    )
        finally:
            capture.release()
        if not frames:
            raise ValueError(f"No frames could be sampled from video: {path}")
        transcript = self._transcribe(path)
        duration = frame_count / fps if fps > 0 else None
        return frames, transcript, {"sampled_frames": len(frames), "duration_seconds": duration}

    @staticmethod
    def _metadata(path: Path, kind: str) -> dict[str, Any]:
        return {"name": path.name, "kind": kind, "size_bytes": path.stat().st_size}
