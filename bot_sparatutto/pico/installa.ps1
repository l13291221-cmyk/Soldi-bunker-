# installa.ps1 - lo usa "AVVIA IL BOT.cmd" (sulla schedina).
# La prima volta scarica il programma del bot in Documenti\BotSparatutto,
# mette un collegamento sul desktop e lo avvia. Le volte dopo lo avvia e basta.
# Se Windows non lascia scrivere in Documenti (per esempio "Accesso alle cartelle
# controllato"), lo mette nella cartella dell'utente: C:\Users\<nome>\BotSparatutto.
# Le TUE impostazioni (impostazioni.yaml, istruzioni.txt, immagini, quello che il
# bot ha imparato) non vengono mai sovrascritte.

$ErrorActionPreference = 'Stop'
$Versione = __VERSIONE__
$Url = '__URL_ZIP__'
$TueImpostazioni = @('impostazioni.yaml', 'istruzioni.txt', 'obiettivo.txt')

function Cartella-Scrivibile($c) {
    # La cartella deve esistere ed essere scrivibile: la provo davvero con un file.
    try {
        if (Test-Path -LiteralPath $c -PathType Leaf) {
            Remove-Item -LiteralPath $c -Force     # un FILE con quel nome (installazione rotta): lo tolgo
        }
        New-Item -ItemType Directory -Force -Path $c | Out-Null
        $prova = Join-Path $c 'prova_scrittura.tmp'
        Set-Content -LiteralPath $prova -Value 'ok'
        Remove-Item -LiteralPath $prova -Force
        return $true
    } catch {
        Write-Host (" Non posso scrivere in " + $c + " (" + $_.Exception.Message + ")")
        return $false
    }
}

$Possibili = @(
    (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'BotSparatutto'),
    (Join-Path $env:USERPROFILE 'BotSparatutto')
)

# gia' installato? lo uso da li'
$Cartella = $null
foreach ($c in $Possibili) {
    if (Test-Path -LiteralPath (Join-Path $c 'BotSparatutto.exe') -PathType Leaf) { $Cartella = $c; break }
}

$Installata = 0
if ($Cartella) {
    $FileVersione = Join-Path $Cartella 'versione.txt'
    if (Test-Path -LiteralPath $FileVersione) {
        [int]::TryParse((Get-Content -LiteralPath $FileVersione -Raw).Trim(), [ref]$Installata) | Out-Null
    }
}

if (-not $Cartella -or $Installata -lt $Versione) {
    if ($Cartella -and -not (Cartella-Scrivibile $Cartella)) { $Cartella = $null }
    if (-not $Cartella) {
        foreach ($c in $Possibili) {
            if (Cartella-Scrivibile $c) { $Cartella = $c; break }
        }
    }
    if (-not $Cartella) { throw "Windows non mi lascia scrivere ne' in Documenti ne' nella cartella dell'utente." }

    Write-Host ' Scarico il programma del bot... (puo'' metterci qualche minuto)'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'
    $Zip = Join-Path $env:TEMP 'BotSparatutto.zip'
    $Temp = Join-Path $env:TEMP 'BotSparatutto_nuovo'
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
    if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
    Write-Host ' Estraggo...'
    Expand-Archive -Path $Zip -DestinationPath $Temp -Force
    $Sorgente = Join-Path $Temp 'BotSparatutto'

    Get-Process BotSparatutto -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host (' Copio in ' + $Cartella + ' ...')
    foreach ($voce in Get-ChildItem -LiteralPath $Sorgente) {
        $dest = Join-Path $Cartella $voce.Name
        if ($voce.PSIsContainer) {
            # una cartella (immagini, modelli, Schedina): i file nuovi si aggiungono, i tuoi restano
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            foreach ($f in Get-ChildItem -LiteralPath $voce.FullName -File) {
                Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $dest $f.Name) -Force
            }
        } elseif ($TueImpostazioni -contains $voce.Name) {
            # le tue impostazioni: solo se non le hai gia'
            if (-not (Test-Path -LiteralPath $dest)) { Copy-Item -LiteralPath $voce.FullName -Destination $dest }
        } else {
            # programma, guida, versione: sempre aggiornati
            Copy-Item -LiteralPath $voce.FullName -Destination $dest -Force
        }
    }
    Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue

    # collegamento sul desktop, per le volte dopo
    try {
        $Desktop = [Environment]::GetFolderPath('Desktop')
        $Shell = New-Object -ComObject WScript.Shell
        $Link = $Shell.CreateShortcut((Join-Path $Desktop 'Bot Sparatutto.lnk'))
        $Link.TargetPath = (Join-Path $Cartella 'BotSparatutto.exe')
        $Link.WorkingDirectory = $Cartella
        $Link.Save()
    } catch { }
    Write-Host (' Fatto! Il bot e'' in ' + $Cartella + ' (e sul desktop: "Bot Sparatutto").')
}

$Exe = Join-Path $Cartella 'BotSparatutto.exe'
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw ("Manca " + $Exe + ": forse l'antivirus l'ha tolto. Guarda in Sicurezza di Windows -> Protezione da virus e minacce -> Cronologia protezione.")
}
Start-Process -FilePath $Exe -WorkingDirectory $Cartella
