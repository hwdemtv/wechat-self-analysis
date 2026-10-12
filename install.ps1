# One-click installer for the wechat-self-analysis WorkBuddy skill (Windows).
# Usage (PowerShell):
#   irm https://github.com/hwdemtv/wechat-self-analysis/raw/main/install.ps1 | iex
$owner = "hwdemtv"
$name = "wechat-self-analysis"
$url = "https://github.com/$owner/$name/archive/refs/heads/main.zip"

$tmp = Join-Path $env:TEMP ($name + "-install")
$dest = Join-Path $env:USERPROFILE ".workbuddy\skills\$name"

try {
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    Write-Host "==> Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile (Join-Path $tmp "$name.zip") -UseBasicParsing

    Write-Host "==> Extracting into $dest"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Expand-Archive -Path (Join-Path $tmp "$name.zip") -DestinationPath $tmp -Force
    Move-Item -Path (Join-Path $tmp "$name-main") -Destination $dest -Force

    Write-Host "==> Installed: $dest"
    Write-Host "==> Running dependency check (install_deps.cmd)"
    $cmd = Join-Path $dest "install_deps.cmd"
    if (Test-Path $cmd) { Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$cmd`"" -Wait }

    Write-Host "==> Done. Restart WorkBuddy to load the skill."
} finally {
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
}
