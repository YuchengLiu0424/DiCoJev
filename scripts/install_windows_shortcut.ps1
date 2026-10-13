[CmdletBinding()]
param(
    [string] $ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string] $ShortcutName = "DiCoJev Decision Studio",
    [string] $AppFolderName = "DiCoJev App"
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$sourceLauncher = Join-Path $resolvedRoot ".venv\Scripts\dicojev-gui.exe"
if (-not (Test-Path -LiteralPath $sourceLauncher -PathType Leaf)) {
    throw "Launcher not found at $sourceLauncher. Run: .\.venv\Scripts\python.exe -m pip install -e ."
}

$appDirectory = Join-Path $resolvedRoot $AppFolderName
New-Item -ItemType Directory -Path $appDirectory -Force | Out-Null
$launcher = Join-Path $appDirectory "DiCoJev.exe"
Copy-Item -LiteralPath $sourceLauncher -Destination $launcher -Force

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
Write-Output $launcher
