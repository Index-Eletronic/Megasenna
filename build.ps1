$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $buildPython = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        $buildPython = (Get-Command python -ErrorAction Stop).Source
    }
    & $buildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam. Compilação cancelada.' }
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build/desktop Megasena.spec
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível gerar o executável.' }
    Write-Host "Executável gerado: $PSScriptRoot\dist\Megasenna\Megasenna.exe"
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build/terminal Terminal.spec
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível gerar o terminal.' }
    Write-Host "Terminal gerado: $PSScriptRoot\dist\Megasena.exe"
} finally {
    Pop-Location
}
