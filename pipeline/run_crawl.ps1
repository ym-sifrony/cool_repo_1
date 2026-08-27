# Scheduled L0 crawl runner (news_rss + telegram_scrape). Registered via
# Windows Task Scheduler to run every few hours -- see spec.md's L0 design:
# RSS/Telegram only ever see what's published going forward, so this needs
# to accumulate over real elapsed time, not one-shot manual runs.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logFile = Join-Path $root "crawl_log.txt"
$ingestDir = Join-Path $root "ingest"

Add-Content -Path $logFile -Value "=== run started: $(Get-Date -Format o) ==="

Push-Location $ingestDir
try {
    python quote_extractor.py 2>&1 | ForEach-Object { Add-Content -Path $logFile -Value $_ }
    python telegram_scrape.py 2>&1 | ForEach-Object { Add-Content -Path $logFile -Value $_ }
} finally {
    Pop-Location
}

Add-Content -Path $logFile -Value "=== run finished: $(Get-Date -Format o) ==="
