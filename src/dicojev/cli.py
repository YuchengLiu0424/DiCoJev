"""Command-line entry points for the v5 runtime."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .api import create_app
from .config import create_agent_runtime, load_config

PACKAGED_DEFAULT_CONFIG = Path(__file__).with_name("default.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dicojev-api",
        description="Serve the DiCoJev v5 decision API against a running local LLaDA-V service.",
    )
    parser.add_argument("--config", default=str(PACKAGED_DEFAULT_CONFIG))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError as error:  # pragma: no cover - depends on optional install
        raise RuntimeError('install DiCoJev with the "api" extra') from error

    runtime = create_agent_runtime(load_config(args.config))
    uvicorn.run(create_app(runtime), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
