# Repository secrets

Secrets consumed by workflows in `.github/workflows/`. Add them under
**Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Used by | Purpose |
|---|---|---|
| `GAMEDATA_PAT` | `canary.yml` | Clone the private `toalba/wows-gamedata` repo over HTTPS. |

PyPI publishing (`publish.yml`) uses **Trusted Publishing** and does **not**
require any secret — it authenticates via OIDC against PyPI directly.

## Generating `GAMEDATA_PAT`

1. Go to <https://github.com/settings/personal-access-tokens/new> (fine-grained token).
2. **Resource owner:** `toalba` (or whichever account owns `wows-gamedata`).
3. **Repository access:** *Only select repositories* → pick `wows-gamedata`.
4. **Repository permissions:** `Contents: Read-only`, `Metadata: Read-only`.
5. **Expiration:** 1 year (set a calendar reminder to rotate).
6. Copy the token, then in this repo: *Settings → Secrets and variables →
   Actions → New repository secret* → name `GAMEDATA_PAT`, paste value, save.

The canary skips cleanly with a workflow warning if the secret is missing, so
rotation lag will not cause spurious failure issues.
