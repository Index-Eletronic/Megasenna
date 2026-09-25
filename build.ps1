$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    py -3.13 -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam. Compilação cancelada.' }
    py -3.13 -m PyInstaller --noconfirm --distpath dist --workpath build/desktop Megasena.spec
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível gerar o executável.' }
    Write-Host "Executável gerado: $PSScriptRoot\dist\Megasenna\Megasenna.exe"
} finally {
    Pop-Location
}
