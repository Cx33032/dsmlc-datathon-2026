# Render the Idea 4 diagram HTML pages to PNG with headless Microsoft Edge.
# Run from the repository root:  powershell -File data/ideas/4/diagrams/render_png.ps1
# Run make_diagrams.py first. Needs internet once for the Google fonts.
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$base = (Resolve-Path "docs\ideas\4\diagrams").Path
$userDir = Join-Path $env:TEMP "idea4-edge-profile"
$pages = @(@("idea4-architecture", 1400, 760), @("idea4-canary-stack", 1180, 880), @("idea4-team-plan", 1440, 760))
foreach ($p in $pages) {
    $name = $p[0]
    $url = "file:///" + $base.Replace("\", "/") + "/$name.html"
    $edgeArgs = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--user-data-dir=$userDir",
                  "--virtual-time-budget=5000", "--window-size=$($p[1]),$($p[2])", "--screenshot=$base\$name.png", $url)
    Start-Process -FilePath $edge -ArgumentList $edgeArgs -Wait -WindowStyle Hidden
    Write-Output "rendered $name.png"
}
