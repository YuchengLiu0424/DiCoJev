[CmdletBinding()]
param(
    [string] $ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string] $ShortcutName = "DiCoJev Decision Studio"
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$launcher = Join-Path $resolvedRoot ".venv\Scripts\dicojev-gui.exe"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Launcher not found at $launcher. Run: .\.venv\Scripts\python.exe -m pip install -e ."
}

$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item("Desktop")
$shortcutPath = Join-Path $desktop ($ShortcutName + ".lnk")
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $resolvedRoot
$shortcut.IconLocation = "$launcher,0"
$shortcut.Description = "Open the native DiCoJev Decision Studio"
$shortcut.Save()

Write-Output $shortcutPath
