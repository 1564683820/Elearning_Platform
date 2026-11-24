[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'check-database', 'check-teaching', 'dev-backend', 'dev-web', 'dev-worker', 'test', 'unit', 'lint', 'typecheck', 'build', 'verify')]
    [string]$Command = 'help'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-External {
    param(
        [Parameter(Mandatory)]
        [string]$Program,
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program $($Arguments -join ' ')"
    }
}

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is unavailable: $Name"
    }
}

function Resolve-BootstrapPython {
    if ($env:CODEX_BUNDLED_PYTHON -and (Test-Path -LiteralPath $env:CODEX_BUNDLED_PYTHON -PathType Leaf)) {
        return $env:CODEX_BUNDLED_PYTHON
    }

    if ($env:USERPROFILE) {
        $CodexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $CodexPython -PathType Leaf) {
            return $CodexPython
        }
    }

    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        return $PythonCommand.Source
    }

    throw 'Required Python interpreter is unavailable.'
}

function Resolve-Python {
    $VirtualEnvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $VirtualEnvPython -PathType Leaf) {
        return $VirtualEnvPython
    }

    return Resolve-BootstrapPython
}

function Show-Help {
    @'
Elearning unified Harness commands

  ./harness.ps1 setup         Install backend and Web dependencies
  ./harness.ps1 check-database Check both databases with read-only SELECT 1
  ./harness.ps1 dev-backend   Start FastAPI on 0.0.0.0:8000
  ./harness.ps1 dev-web       Start the Vite development server
  ./harness.ps1 test          Parse all backend Python files (syntax only)
  ./harness.ps1 unit          Run backend unittest regression suite
  ./harness.ps1 check-teaching Read-only teaching environment readiness check
  ./harness.ps1 dev-worker    Start the durable teaching task worker
  ./harness.ps1 lint          Validate the Harness control plane
  ./harness.ps1 typecheck     Run the Web TypeScript project check
  ./harness.ps1 build         Build the Web production bundle
  ./harness.ps1 verify        Run all non-writing checks (lint, syntax, typecheck)

Run commands from the repository root. Full integration testing still requires
the services and credentials documented in .harness/wiki/项目地图.md.
'@
}

function Invoke-Setup {
    $BootstrapPython = Resolve-BootstrapPython
    $VirtualEnvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    Assert-Command npm
    Push-Location $ProjectRoot
    try {
        if (-not (Test-Path -LiteralPath $VirtualEnvPython -PathType Leaf)) {
            Invoke-External $BootstrapPython -m venv .venv
        }
        Invoke-External $VirtualEnvPython -m pip install --no-cache-dir -r server/requirements.txt
        Invoke-External npm --prefix client ci
    }
    finally {
        Pop-Location
    }
}

function Invoke-BackendDev {
    $Python = Resolve-Python
    Push-Location (Join-Path $ProjectRoot 'server')
    try {
        Invoke-External $Python (Join-Path $ProjectRoot '.harness/scripts/check-database.py')
        Invoke-External $Python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    }
    finally {
        Pop-Location
    }
}

function Invoke-WebDev {
    Assert-Command npm
    Push-Location $ProjectRoot
    try {
        Invoke-External npm --prefix client run dev
    }
    finally {
        Pop-Location
    }
}

function Invoke-BackendCheck {
    $Python = Resolve-Python
    Write-Host 'Running no-write Python syntax regression; use unit for behavioral tests.'
    Push-Location $ProjectRoot
    try {
        Write-Host "Python runtime: $Python"
        Invoke-External $Python .harness/scripts/python-syntax.py server/app
    }
    finally {
        Pop-Location
    }
}

function Invoke-HarnessLint {
    Push-Location $ProjectRoot
    try {
        & (Join-Path $ProjectRoot '.harness/scripts/validate.ps1')
        if ($LASTEXITCODE -ne 0) {
            throw "Harness validation failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-Typecheck {
    $TypeScript = Join-Path $ProjectRoot 'client/node_modules/.bin/tsc.cmd'
    if (-not (Test-Path -LiteralPath $TypeScript -PathType Leaf)) {
        throw "TypeScript compiler is unavailable at $TypeScript. Run './harness.ps1 setup' first."
    }
    Push-Location (Join-Path $ProjectRoot 'client')
    try {
        Invoke-External $TypeScript --project tsconfig.json --pretty false
    }
    finally {
        Pop-Location
    }
}

function Invoke-WebBuild {
    Assert-Command npm
    Push-Location $ProjectRoot
    try {
        Invoke-External npm --prefix client run build
    }
    finally {
        Pop-Location
    }
}

switch ($Command) {
    'help' { Show-Help }
    'setup' { Invoke-Setup }
    'check-database' { Invoke-External (Resolve-Python) (Join-Path $ProjectRoot '.harness/scripts/check-database.py') }
    'check-teaching' { Invoke-External (Resolve-Python) (Join-Path $ProjectRoot 'server/scripts/teaching_preflight.py') }
    'unit' {
        Push-Location (Join-Path $ProjectRoot 'server')
        try { Invoke-External -Program (Resolve-Python) -Arguments @('-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-q') }
        finally { Pop-Location }
    }
    'dev-worker' {
        Push-Location (Join-Path $ProjectRoot 'server')
        try {
            Invoke-External (Resolve-Python) scripts/teaching_preflight.py
            Invoke-External (Resolve-Python) -m app.teaching_worker
        }
        finally { Pop-Location }
    }
    'dev-backend' { Invoke-BackendDev }
    'dev-web' { Invoke-WebDev }
    'test' { Invoke-BackendCheck }
    'lint' { Invoke-HarnessLint }
    'typecheck' { Invoke-Typecheck }
    'build' { Invoke-WebBuild }
    'verify' {
        Invoke-HarnessLint
        Invoke-BackendCheck
        Invoke-Typecheck
    }
}
