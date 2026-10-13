# Security Policy

## Supported version

Security fixes are applied to the latest release line. Older research milestones are retained for
reproducibility but are not independently maintained.

## Reporting a vulnerability

Please do not open a public issue for an unpatched vulnerability or suspected credential exposure.
Use GitHub's private vulnerability-reporting feature for this repository. If that feature is not
available, contact the maintainer through the address in the repository's Git commit metadata and
include only the minimum information required to reproduce the problem.

Do not include API keys, private prompts, user databases, model credentials, or raw media in a
report. Provide redacted logs and synthetic reproductions whenever possible.

## Security boundaries

- Cloud API keys entered in the Windows desktop application are stored with Windows DPAPI.
- Local profiles, chats, and usage records remain in the selected local data directory.
- Project file access is path-confined and read-only unless write access is explicitly granted.
- Arbitrary shell execution and implicit desktop control are not enabled.
- Image-derived text is sent to cloud models only after the desktop obtains user consent; original
  image bytes remain local on the text-only fallback route.
