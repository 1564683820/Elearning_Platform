set shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

# List the available development commands.
default:
    @just --list

# Start the Web admin only.
dev-web:
    ./harness.ps1 dev-web

# Start the H5 client only.
dev-h5: _require-h5
    npm --prefix client/h5 run dev

# Start Web and H5 together after checking H5 is available.
dev: _require-h5 && _dev-frontends

# Start FastAPI separately.
dev-backend:
    ./harness.ps1 dev-backend

[private]
_require-h5:
    @if (-not (Test-Path -LiteralPath 'client/h5/package.json' -PathType Leaf)) { throw 'H5 is not available yet. Expected client/h5/package.json with a dev script.' }
    @if (-not (Get-Content -Raw -LiteralPath 'client/h5/package.json' | ConvertFrom-Json).scripts.dev) { throw 'H5 package.json must define scripts.dev.' }

[private]
[parallel]
_dev-frontends: dev-web dev-h5
