# Contributing to DiCoJev

Thank you for considering a contribution. Start with the complete
[contribution guide](docs/governance/CONTRIBUTING.md), which explains the project contracts,
documentation ownership, testing expectations, and pull-request checklist.

For a normal development setup:

```bash
python -m venv .venv
python -m pip install -e ".[dev,api]"
python -m pytest
```

Never commit API keys, local credentials, model weights, private prompts, or raw user media.
