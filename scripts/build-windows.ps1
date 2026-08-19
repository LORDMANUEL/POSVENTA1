$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3.12+ no está instalado o no está en PATH.'
}

python -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\python.exe -m pip install -r desktop\requirements.txt
& .\.venv-build\Scripts\python.exe -m pip install -e 'agent[build]'

New-Item -ItemType Directory -Force -Path dist-windows | Out-Null

$launchers = @(
    @{ Name = 'MilyZebra-Cajera'; Mode = 'cashier' },
    @{ Name = 'MilyZebra-Vendedor'; Mode = 'sales' },
    @{ Name = 'MilyZebra-Bodeguero'; Mode = 'warehouse' },
    @{ Name = 'MilyZebra-Driver'; Mode = 'driver' }
)

foreach ($launcher in $launchers) {
    & .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed `
        --name $launcher.Name desktop\launcher.py
    Move-Item -Force (Join-Path 'dist' ($launcher.Name + '.exe')) 'dist-windows\'
}

& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean --onefile --console `
    --name 'MilyZebra-Hardware-Agent' agent\mily_agent.py
Move-Item -Force 'dist\MilyZebra-Hardware-Agent.exe' 'dist-windows\'

Write-Host 'Ejecutables generados en dist-windows:'
Get-ChildItem dist-windows\*.exe | Select-Object Name, Length
