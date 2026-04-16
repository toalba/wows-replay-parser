# Security Policy

## Supported Versions

While the project is pre-1.0, only the `main` branch receives security fixes.
Once tagged releases begin, the most recent minor line will be supported.

## Reporting a Vulnerability

**Do not file public GitHub issues for security problems.**

Prefer the private channel:

1. GitHub → this repo → **Security → Report a vulnerability** (GitHub
   Security Advisories, maintainer-only visibility).
2. Fallback email: **tb@kleinundpartner.at**.

Please include:
- A description of the issue and its impact.
- Steps to reproduce, ideally with a minimal proof-of-concept.
- Affected version(s) / commit SHA.
- Any mitigations you're aware of.

## Response

- Acknowledgement within **72 hours**.
- Triage and severity assessment within **7 days**.
- Fix or mitigation for confirmed vulnerabilities within **30 days**, faster
  for high-severity issues.

Coordinated disclosure is expected: please allow a reasonable window for a
fix to ship before going public. Credit is given in release notes unless
the reporter prefers anonymity.

## Out of Scope

- End-user compliance with Wargaming's EULA for the World of Warships
  client. This project consumes replay files; it is the user's
  responsibility to use them lawfully.
- Integrity / provenance of the `wows-gamedata` repository. That is a
  separate project with its own policy.
