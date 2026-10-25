# Starts everything: engine, Presage bridge, web app and (unless -NoTunnel) the Cloudflare tunnel for phones.
# Each service gets its own window so you can see its log; close a window to stop that service.
#
#   .\scripts\start.ps1              all four, then prints the https address to open
#   .\scripts\start.ps1 -NoTunnel    local only (http://localhost:3000)
#   .\scripts\start.ps1 -Prod        production web build (faster on a phone than the dev server)
#   .\scripts\start.ps1 -Stop        close everything this script started
param([switch]$NoTunnel, [switch]$Prod, [switch]$Stop)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv\Scripts"
$PidFile = Join-Path $Root "logs\start.pids"
$TunnelLog = Join-Path $Root "logs\tunnel.log"
New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null

if ($Stop) {
    if (Test-Path $PidFile) {
        Get-Content $PidFile | ForEach-Object { taskkill /PID $_ /T /F 2>$null | Out-Null }
        Remove-Item $PidFile
        "Stopped."
    } else { "Nothing recorded as running." }
    return
}

if (-not (Test-Path (Join-Path $Venv "python.exe"))) { throw "No .venv at $Venv. Create it first: python -m venv .venv" }
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Warning ".env not found in the repo root. Services will run in mock mode (no Gemini, no Presage). See README 'Settings'."
}

# the venv's Scripts folder carries python, uvicorn and (here) node/npm; npm's install scripts need node on PATH too
$env:Path = "$Venv;" + $env:Path
$Path ="`$env:Path = '$Venv;' + `$env:Path"

function Start-Service($title, $dir, $command) {
    $script = "$Path; `$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $command"
    $p = Start-Process powershell -ArgumentList "-NoExit", "-Command", $script -PassThru
    Add-Content $PidFile $p.Id
    $p
}

function Wait-Url($url, $name, $seconds = 120) {
    $until = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $until) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 | Out-Null; "  $name is up"; return }
        catch { Start-Sleep -Seconds 2 }
    }
    Write-Warning "$name did not answer at $url within $seconds s; check its window."
}

if (Test-Path $PidFile) { Remove-Item $PidFile }

# first run: install what is missing
foreach ($d in "web", "presage-bridge") {
    if (-not (Test-Path (Join-Path $Root "$d\node_modules\.package-lock.json")) -and
        -not (Test-Path (Join-Path $Root "$d\node_modules\next")) -and
        -not (Test-Path (Join-Path $Root "$d\node_modules\ws"))) {
        "Installing $d dependencies (first run)..."
        Push-Location (Join-Path $Root $d)
        & (Join-Path $Venv "npm.cmd") install
        Pop-Location
    }
}

"Starting engine..."
Start-Service "AtollCare engine" (Join-Path $Root "engine") "python -m uvicorn app.main:app --port 8000" | Out-Null
"Starting Presage bridge..."
Start-Service "AtollCare Presage bridge" (Join-Path $Root "presage-bridge") "node --env-file=../.env src/index.js" | Out-Null
"Starting web app..."
$webCmd = if ($Prod) { "npm run build; npm run start" } else { "npm run dev" }
Start-Service "AtollCare web" (Join-Path $Root "web") $webCmd | Out-Null

"Waiting for services (the first web start compiles, so give it a minute)..."
Wait-Url "http://localhost:8000/api/health" "engine" 60
Wait-Url "http://localhost:8787/health" "Presage bridge" 60
Wait-Url "http://localhost:3000/api/health" "web + engine proxy" 300

$address = "http://localhost:3000"
if (-not $NoTunnel) {
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Write-Warning "cloudflared isn't installed (winget install --id Cloudflare.cloudflared). Phones need it; continuing local-only."
    } else {
        if (Test-Path $TunnelLog) { Remove-Item $TunnelLog }
        $t = Start-Process $cf.Source -ArgumentList "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://localhost:3000" `
            -RedirectStandardError $TunnelLog -RedirectStandardOutput (Join-Path $Root "logs\tunnel.out.log") -WindowStyle Hidden -PassThru
        Add-Content $PidFile $t.Id
        "Opening the tunnel..."
        $until = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $until -and $address -eq "http://localhost:3000") {
            Start-Sleep -Seconds 2
            if (Test-Path $TunnelLog) {
                $m = Select-String -Path $TunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
                if ($m) { $address = $m.Matches[0].Value }
            }
        }
        if ($address -eq "http://localhost:3000") { Write-Warning "No tunnel address appeared; see $TunnelLog" }
    }
}

""
"Ready."
"  Open on this laptop:  $address"
if ($address -like "https://*") {
    "  Then press Ctrl + .  and scan the 'On a phone' QR code with your phone."
    "  (Open the https address on the laptop, not localhost, or the QR will encode localhost.)"
}
"  Stop everything:      .\scripts\start.ps1 -Stop"
Start-Process $address
