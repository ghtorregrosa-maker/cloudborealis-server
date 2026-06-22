Write-Host "=== ESTRUCTURA ===" -ForegroundColor Cyan
Get-ChildItem -Recurse -File -Include *.py,*.json,*.yaml,*.yml,*.txt,*.md | Format-Table FullName, Length -AutoSize

Write-Host "`n=== mind.py ===" -ForegroundColor Green
if (Test-Path "mind.py") { Get-Content "mind.py" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== app.py ===" -ForegroundColor Green
if (Test-Path "app.py") { Get-Content "app.py" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== main.py ===" -ForegroundColor Green
if (Test-Path "main.py") { Get-Content "main.py" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== requirements.txt ===" -ForegroundColor Green
if (Test-Path "requirements.txt") { Get-Content "requirements.txt" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== config.json ===" -ForegroundColor Green
if (Test-Path "config.json") { Get-Content "config.json" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== config.yaml ===" -ForegroundColor Green
if (Test-Path "config.yaml") { Get-Content "config.yaml" } else { Write-Host "NO ENCONTRADO" -ForegroundColor Red }

Write-Host "`n=== OTROS .py ===" -ForegroundColor Yellow
Get-ChildItem -Filter "*.py" | Where-Object { $_.Name -notin @("mind.py", "app.py", "main.py") } | ForEach-Object {
    Write-Host "`n--- $($_.Name) ---" -ForegroundColor Green
    Get-Content $_.FullName
}

Write-Host "`n=== FIN ===" -ForegroundColor Cyan