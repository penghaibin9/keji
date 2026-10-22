param([Parameter(Mandatory=$true)][string]$InputFile,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Huihui Desktop')
    $speaker.Rate = 1
    $segments = Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8 | ConvertFrom-Json
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    for ($segmentIndex=0; $segmentIndex -lt $segments.Count; $segmentIndex++) {
        $speaker.SetOutputToWaveFile((Join-Path $OutputDirectory "$segmentIndex.wav"))
        $speaker.Speak([string]$segments[$segmentIndex].text)
        $speaker.SetOutputToNull()
    }
} finally { $speaker.Dispose() }
