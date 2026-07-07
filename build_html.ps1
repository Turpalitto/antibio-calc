# Build antibiotic_calc.html from template + DB
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File build_html.ps1

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$tpl   = Join-Path $root 'antibiotic_calc.html.template'
$db    = Join-Path $root 'db\antibio_db.json'
$out   = Join-Path $root 'antibiotic_calc.html'

if(-not (Test-Path -LiteralPath $tpl)) { throw "Template not found: $tpl" }
if(-not (Test-Path -LiteralPath $db))  { throw "DB not found: $db" }

# Validate JSON first
$null = Get-Content -LiteralPath $db -Raw -Encoding UTF8 | ConvertFrom-Json

# Read raw JSON (one-line, UTF-8 no BOM)
$json = Get-Content -LiteralPath $db -Raw -Encoding UTF8
$json = $json.Trim()

# Read template
$html = Get-Content -LiteralPath $tpl -Raw -Encoding UTF8

# Replace placeholder
if(-not $html.Contains('__DB_PLACEHOLDER__')) { throw "Placeholder __DB_PLACEHOLDER__ not found in template" }
$final = $html.Replace('__DB_PLACEHOLDER__', $json)

# Write output (UTF-8 no BOM)
[System.IO.File]::WriteAllText($out, $final, [System.Text.UTF8Encoding]::new($false))

$size = (Get-Item -LiteralPath $out).Length
Write-Host "Built: $out"
Write-Host ("Size: {0:N1} KB" -f ($size/1KB))
Write-Host "DB embedded: $($json.Length) chars"
