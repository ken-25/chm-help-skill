<#
.SYNOPSIS
  Convert CHM help (or a folder of plain help pages) into a Markdown skill
  folder, or into one self-contained HTML file per page.
.EXAMPLE
  .\convert.ps1 -Chm "C:\Program Files\Example\Help\example.chm" `
                -Out ".\skills\example-help" -Name example-help -Title "Example App"
.EXAMPLE
  .\convert.ps1 -Chm "C:\Program Files\Example\Help\example.chm" `
                -Out ".\html\example" -Format html -Title "Example App"
#>
param(
    [string] $Chm,
    [string] $SrcDir,
    [Parameter(Mandatory)] [string] $Out,
    [ValidateSet('md', 'html')] [string] $Format = 'md',
    [string] $Name,
    [Parameter(Mandatory)] [string] $Title,
    [switch] $WithImages,
    [string] $ClassMap
)
$ErrorActionPreference = 'Stop'
if ([bool]$Chm -eq [bool]$SrcDir) { throw 'Give exactly one of -Chm or -SrcDir.' }
$argsList = @('run', '--project', $PSScriptRoot, 'python', (Join-Path $PSScriptRoot 'chm2md.py'),
              '--out', $Out, '--format', $Format, '--title', $Title)
if ($Chm)        { $argsList += @('--chm', $Chm) }
if ($SrcDir)     { $argsList += @('--src-dir', $SrcDir) }
if ($Name)       { $argsList += @('--name', $Name) }
if ($WithImages) { $argsList += '--with-images' }
if ($ClassMap)   { $argsList += @('--class-map', $ClassMap) }
& uv @argsList
exit $LASTEXITCODE
