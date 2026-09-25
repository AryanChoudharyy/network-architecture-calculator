param(
    [Parameter(Position=0, Mandatory=$true)][string]$Program,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ProgramArgs
)
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot $Program
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Program not found: $scriptPath"
}
$bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pyCommand) {
    & $pyCommand.Source -3 $scriptPath @ProgramArgs
} elseif ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
    & $pythonCommand.Source $scriptPath @ProgramArgs
} elseif (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython $scriptPath @ProgramArgs
} else {
    throw 'Python 3.10+ is required. Install Python and add it to PATH.'
}
exit $LASTEXITCODE
