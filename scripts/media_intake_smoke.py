"""Exercise local attachment preprocessing without running the decision model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dicojev.multimedia import LocalMediaIngestor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("attachments", nargs="+", type=Path)
    parser.add_argument("--speech-model", default=None)
    parser.add_argument("--video-frames", type=int, default=4)
    args = parser.parse_args()
    result = LocalMediaIngestor(
        speech_model=args.speech_model, video_frames=args.video_frames
    ).ingest([str(path) for path in args.attachments])
    print(
        json.dumps(
            {
                "attachments": result.metadata,
                "text_blocks": len(result.text_blocks),
                "text_characters": sum(len(block) for block in result.text_blocks),
                "native_images": len(result.images),
                "image_media_types": [image.media_type for image in result.images],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
