# run_patch.ps1
# Corre apply_patch.py para insertar _handle_code() en executor.py
# y valida que todo haya quedado con sintaxis correcta.

$py = "C:\Users\Usuario\AppData\Local\Programs\Python\Python312\python.exe"
$deploy = "F:\sistema completo - copia\deploy_render"

Write-Host "== Aplicando parche a executor.py ==" -ForegroundColor Cyan
& $py "$deploy\apply_patch.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nEl parche NO se aplico correctamente. Revisar el mensaje de error de arriba." -ForegroundColor Red
    exit 1
}

Write-Host "`n== Verificacion final de sintaxis ==" -ForegroundColor Cyan
& $py -c "import ast; ast.parse(open(r'$deploy\executor.py', encoding='utf-8').read()); print('OK')"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nListo. executor.py quedo parcheado y validado." -ForegroundColor Green
    Write-Host "Backup del original en: $deploy\executor.py.bak" -ForegroundColor DarkGray
    Write-Host "`nProximo paso sugerido:" -ForegroundColor Yellow
    Write-Host "  git add -A"
    Write-Host "  git commit -m 'Agrega handler de generacion de codigo (_handle_code)'"
    Write-Host "  git push origin main"
} else {
    Write-Host "`nQuedo un problema de sintaxis. Revisar executor.py.bak como referencia." -ForegroundColor Red
}
