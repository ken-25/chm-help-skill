<#
.SYNOPSIS
  Convert a CHM help file into a Markdown skill folder.
.EXAMPLE
  .\convert.ps1 -Chm "C:\Program Files\Example\Help\example.chm" `
                -Out ".\skills\example-help" -Name example-help -Title "Example App"
#>
param(
    [Parameter(Mandatory)] [string] $Chm,
    [Parameter(Mandatory)] [string] $Out,
    [Parameter(Mandatory)] [string] $Name,
    [Parameter(Mandatory)] [string] $Title,
    [switch] $WithImages,
    [string] $ClassMap
)
$ErrorActionPreference = 'Stop'
$argsList = @('run', '--project', $PSScriptRoot, 'python', (Join-Path $PSScriptRoot 'chm2md.py'),
              '--chm', $Chm, '--out', $Out, '--name', $Name, '--title', $Title)
if ($WithImages) { $argsList += '--with-images' }
if ($ClassMap)   { $argsList += @('--class-map', $ClassMap) }
& uv @argsList
exit $LASTEXITCODE
