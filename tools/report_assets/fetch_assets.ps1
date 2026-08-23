<#
  Re-vendors the runtime assets the HTML audit report inlines, into
  agent_guardian/templates/vendor/:

    * chart.umd.min.js              — pinned Chart.js UMD build
    * material-symbols-subset.woff2 — Material Symbols, subsetted to ONLY the
                                      icon names the report actually uses

  The Tailwind stylesheet (report.css) is built separately: `npm run build`.

  Run from anywhere:  pwsh tools/report_assets/fetch_assets.ps1
  Requires network access to jsdelivr + Google Fonts.

  NOTE: if you add a NEW material-symbols icon name to report_template.html,
  html_structurizers.py or html_agent.py, add it to $Icons below and re-run, or
  that glyph will be missing from the subset and render as text.
#>
[CmdletBinding()]
param(
  [string] $ChartVersion = "4.4.9"
)

$ErrorActionPreference = "Stop"
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
$vendor = Join-Path $PSScriptRoot "..\..\agent_guardian\templates\vendor"
New-Item -ItemType Directory -Force $vendor | Out-Null

# Every material-symbols ligature used across the report + structurizers.
$Icons = @(
  "account_tree","analytics","bolt","cancel","clinical_notes","code_blocks","dashboard","error",
  "expand_more","fact_check","flag","gavel","gpp_good","groups","hub","layers",
  "list_alt","menu_book","print","remove_circle","robot_2","security",
  "security_update_warning","shield_with_heart","summarize","terminal","verified",
  "verified_user","visibility","warning"
) -join " "

function Get-WithRetry($uri, $outFile) {
  for ($i = 1; $i -le 5; $i++) {
    try { Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers @{ "User-Agent" = $ua } -OutFile $outFile -TimeoutSec 30; return }
    catch { Write-Host "  attempt $i failed: $($_.Exception.Message)"; Start-Sleep -Seconds 2 }
  }
  throw "Failed to download $uri after 5 attempts"
}

Write-Host "Vendoring Chart.js v$ChartVersion ..."
Get-WithRetry "https://cdn.jsdelivr.net/npm/chart.js@$ChartVersion/dist/chart.umd.min.js" (Join-Path $vendor "chart.umd.min.js")

Write-Host "Vendoring subsetted Material Symbols font ($($Icons.Split(' ').Count) icons) ..."
$enc = [uri]::EscapeDataString($Icons)
# No variable-axis ranges: requesting the full axes returns the whole ~4MB font.
# The default-instance subset is ~260KB and renders outline icons (FILL is dropped).
$cssUrl = "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined&text=$enc&display=block"
for ($i = 1; $i -le 5; $i++) {
  try {
    $css  = (Invoke-WebRequest -UseBasicParsing -Uri $cssUrl -Headers @{ "User-Agent" = $ua }).Content
    $woff = [regex]::Match($css, "src:\s*url\(([^)]+)\)").Groups[1].Value
    Get-WithRetry $woff (Join-Path $vendor "material-symbols-subset.woff2")
    break
  } catch { Write-Host "  css attempt $i failed: $($_.Exception.Message)"; Start-Sleep -Seconds 2 }
}

Write-Host "Done. Vendor contents:"
Get-ChildItem $vendor | Select-Object Name, @{ n = "KB"; e = { [math]::Round($_.Length / 1024, 1) } } | Format-Table -AutoSize
