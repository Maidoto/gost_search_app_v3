param(
    [switch]$Once,
    [switch]$Preview,
    [switch]$SessionString
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

$Script = Join-Path $ProjectRoot "clock_avatar.py"
$ArgsList = @()

if ($Once) {
    $ArgsList += "--once"
}

if ($Preview) {
    $ArgsList += "--preview"
}

if ($SessionString) {
    $ArgsList += "--session-string"
}

& $Python $Script @ArgsList
