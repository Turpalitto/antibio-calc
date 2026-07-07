# AntibioDB — build & merge script
# Собирает все disease-файлы + drugs_reference в единый antibio_db.json
# Запуск: pwsh -File build_db.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$diseasesDir = Join-Path $root 'diseases'
$outFile = Join-Path $root 'antibio_db.json'

# 1. Загрузить index (meta + drugs_reference)
$index = Get-Content -LiteralPath (Join-Path $root 'index.json') -Raw -Encoding UTF8 | ConvertFrom-Json

# 2. Собрать все рекомендации из diseases/*.json
$allRecs = New-Object System.Collections.Generic.List[object]
$diseaseFiles = Get-ChildItem -LiteralPath $diseasesDir -Filter '*.json' | Sort-Object Name
$categories = New-Object System.Collections.Generic.List[object]

foreach ($f in $diseaseFiles) {
    $obj = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $categories.Add([pscustomobject]@{
        file     = $f.Name
        category = $obj.category
        count    = $obj.recommendations.Count
    })
    foreach ($r in $obj.recommendations) {
        $allRecs.Add($r)
    }
}

# 3. Собрать финальный объект
$db = [ordered]@{
    meta           = $index.meta
    drugs_reference = $index.drugs_reference
    categories     = $categories
    recommendations = $allRecs
}

# 4. Записать
$json = $db | ConvertTo-Json -Depth 12 -Compress
Set-Content -LiteralPath $outFile -Value $json -Encoding UTF8 -NoNewline

# 5. Валидация
$null = Get-Content -LiteralPath $outFile -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host "Build OK: $outFile"
Write-Host "Recommendations: $($allRecs.Count)"
Write-Host "Drugs in reference: $(($index.drugs_reference.PSObject.Properties | Where-Object {$_.Name -ne '_note'}).Count)"
Write-Host ""
Write-Host "Categories:"
$categories | ForEach-Object { "  - $($_.category): $($_.count) recommendations ($($_.file))" }
