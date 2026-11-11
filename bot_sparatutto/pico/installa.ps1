# installa.ps1 - lo usa "AVVIA IL BOT.cmd" (sulla schedina).
# La prima volta scarica il programma del bot in Documenti\BotSparatutto,
# mette un collegamento sul desktop e lo avvia. Le volte dopo lo avvia e basta.
# Le TUE impostazioni (impostazioni.yaml, istruzioni.txt, immagini, quello che il
# bot ha imparato) non vengono mai sovrascritte.

$ErrorActionPreference = 'Stop'
$Versione = __VERSIONE__
$Url = '__URL_ZIP__'

$Cartella = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'BotSparatutto'
$Exe = Join-Path $Cartella 'BotSparatutto.exe'
$FileVersione = Join-Path $Cartella 'versione.txt'

$Installata = 0
if (Test-Path $FileVersione) {
    [int]::TryParse((Get-Content $FileVersione -Raw).Trim(), [ref]$Installata) | Out-Null
}

if (-not (Test-Path $Exe) -or $Installata -lt $Versione) {
    Write-Host ' Scarico il programma del bot... (puo'' metterci qualche minuto)'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'
    $Zip = Join-Path $env:TEMP 'BotSparatutto.zip'
    $Temp = Join-Path $env:TEMP 'BotSparatutto_nuovo'
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
    if (Test-Path $Temp) { Remove-Item $Temp -Recurse -Force }
    Write-Host ' Estraggo...'
    Expand-Archive -Path $Zip -DestinationPath $Temp -Force
    $Sorgente = Join-Path $Temp 'BotSparatutto'

    Get-Process BotSparatutto -ErrorAction SilentlyContinue | Stop-Process -Force
    New-Item -ItemType Directory -Force -Path $Cartella | Out-Null
    # programma, occhio universale e guida: sempre aggiornati
    Get-ChildItem $Sorgente | Where-Object { $_.Name -notin @('impostazioni.yaml', 'istruzioni.txt') } |
        ForEach-Object { Copy-Item $_.FullName $Cartella -Recurse -Force }
    # le tue impostazioni: solo se non le hai gia'
    foreach ($f in @('impostazioni.yaml', 'istruzioni.txt')) {
        if (-not (Test-Path (Join-Path $Cartella $f))) { Copy-Item (Join-Path $Sorgente $f) $Cartella }
    }
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue

    # collegamento sul desktop, per le volte dopo
    try {
        $Desktop = [Environment]::GetFolderPath('Desktop')
        $Shell = New-Object -ComObject WScript.Shell
        $Link = $Shell.CreateShortcut((Join-Path $Desktop 'Bot Sparatutto.lnk'))
        $Link.TargetPath = $Exe
        $Link.WorkingDirectory = $Cartella
        $Link.Save()
    } catch { }
    Write-Host ' Fatto! Il bot e'' in Documenti\BotSparatutto (e sul desktop: "Bot Sparatutto").'
}

Start-Process -FilePath $Exe -WorkingDirectory $Cartella
