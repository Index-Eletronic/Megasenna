$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $buildPython = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        $buildPython = (Get-Command python -ErrorAction Stop).Source
    }
    & $buildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam. Compilação cancelada.' }
    # Preserve a distribuição anterior e o banco antes de substituir executáveis.
    $backupDirectory = Join-Path $PSScriptRoot ('build\backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff'))
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    if (Test-Path -LiteralPath 'dist\Megasena.exe') {
        Copy-Item -LiteralPath 'dist\Megasena.exe' -Destination $backupDirectory
    }
    if (Test-Path -LiteralPath 'dist\Megasenna') {
        Copy-Item -LiteralPath 'dist\Megasenna' -Destination $backupDirectory -Recurse
    }
    & $buildPython -c "from pathlib import Path; from megasena import storage; print(storage.criar_backup('compilacao')) if Path(storage.DB_PATH).is_file() else None"
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível salvar o backup do banco. Compilação cancelada.' }
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build/desktop Megasena.spec
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível gerar o executável.' }
    Write-Host "Executável gerado: $PSScriptRoot\dist\Megasenna\Megasenna.exe"
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build/terminal Terminal.spec
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível gerar o terminal.' }
    Write-Host "Terminal gerado: $PSScriptRoot\dist\Megasena.exe"
    New-Item -ItemType Directory -Path 'dist\carteiras' -Force | Out-Null
    Get-ChildItem -LiteralPath 'assets' -Filter 'carteira-*.json' -File | Copy-Item -Destination 'dist\carteiras'
} finally {
    Pop-Location
}
