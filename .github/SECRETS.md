# Repository secrets

Secrets consumed by workflows in `.github/workflows/`.

Currently no custom secrets are required:

- `canary.yml` clones the public [`wows-render-gamedata`](https://github.com/toalba/wows-render-gamedata) repo and needs no authentication.
- `publish.yml` uses **Trusted Publishing** via OIDC against PyPI — no secret required.

The `GAMEDATA_PAT` secret previously used to access the private gamedata repo is no longer needed and can be removed under *Settings → Secrets and variables → Actions* if it still exists.
