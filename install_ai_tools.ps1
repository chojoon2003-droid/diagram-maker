# 건축 이미지 에이전트 - AI 도구 설치기
# Python, Node.js, Claude Code, Codex 를 확인하고 없는 것만 설치합니다.
# 실행: install_ai_tools.bat 더블클릭 (관리자 권한 필요 없음)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Say($msg, $color = "White") { Write-Host $msg -ForegroundColor $color }
function Step($n, $msg) { Write-Host ""; Write-Host "[$n/5] $msg" -ForegroundColor Cyan }

function Refresh-Path {
    # 방금 설치한 프로그램을 이 창에서 바로 찾을 수 있게 PATH 다시 읽기
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $extra = @("$env:USERPROFILE\.local\bin", "$env:APPDATA\npm", "$env:ProgramFiles\nodejs")
    $env:Path = (@($machine, $user) + $extra | Where-Object { $_ }) -join ";"
}

function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Version($cmd, $arg = "--version") {
    try { return ((& $cmd $arg 2>$null) | Select-Object -First 1).ToString().Trim() } catch { return "" }
}

function Winget-Install($id, $name) {
    if (-not (Has "winget")) {
        Say "  winget이 없어 자동 설치를 못 해요. 열리는 페이지에서 $name 을(를) 직접 설치한 뒤 이 설치기를 다시 실행하세요." Yellow
        return $false
    }
    Say "  $name 설치 중... (몇 분 걸릴 수 있어요)"
    winget install -e --id $id --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
    return $true
}

$results = [ordered]@{}
Say "==============================================" Green
Say "  건축 이미지 에이전트 - AI 도구 설치기" Green
Say "  (이미 설치된 것은 건너뛰어요)" Green
Say "==============================================" Green
Refresh-Path

# ---------------------------------------------------------------- 1. Python
Step 1 "Python (에이전트 실행용)"
$py = (Has "py") -or ((Has "python") -and ((Version "python") -match "Python 3"))
if ($py) {
    Say "  이미 있어요." Green
} else {
    if (-not (Winget-Install "Python.Python.3.12" "Python")) { Start-Process "https://www.python.org/downloads/" }
    $py = (Has "py") -or ((Has "python") -and ((Version "python") -match "Python 3"))
}
$results["Python"] = if ($py) { "OK" } else { "설치 필요 (창을 새로 연 뒤 다시 확인)" }

# ---------------------------------------------------------------- 2. Node.js
Step 2 "Node.js (Codex 설치에 필요)"
$nodeOk = $false
if (Has "node") {
    $nv = Version "node"
    if ($nv -match "v(\d+)\." -and [int]$Matches[1] -ge 18) { $nodeOk = $true; Say "  이미 있어요 ($nv)." Green }
    else { Say "  버전이 낮아요 ($nv). LTS 버전으로 설치할게요." Yellow }
}
if (-not $nodeOk) {
    if (-not (Winget-Install "OpenJS.NodeJS.LTS" "Node.js LTS")) { Start-Process "https://nodejs.org/" }
    $nodeOk = (Has "node")
}
$results["Node.js"] = if ($nodeOk) { "OK ($(Version 'node'))" } else { "설치 필요" }

# ---------------------------------------------------------------- 3. Claude Code
Step 3 "Claude Code (검토·검수, Claude 유료 구독)"
if (Has "claude") {
    Say "  이미 있어요 ($(Version 'claude'))." Green
} else {
    Say "  Claude Code 설치 중... (공식 설치 스크립트)"
    try {
        Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    } catch {
        Say "  설치 중 오류: $($_.Exception.Message)" Red
    }
    Refresh-Path
}
$results["Claude Code"] = if (Has "claude") { "OK ($(Version 'claude'))" } else { "설치 실패 - 창을 새로 열고 'claude --version' 확인" }

# ---------------------------------------------------------------- 4. Codex
Step 4 "Codex (이미지 생성, ChatGPT 구독)"
if (Has "codex") {
    Say "  이미 있어요 ($(Version 'codex'))." Green
} elseif (-not (Has "npm")) {
    Say "  Node.js(npm)가 없어 Codex를 설치할 수 없어요. Node.js 설치 후 이 설치기를 다시 실행하세요." Yellow
} else {
    Say "  Codex 설치 중... (npm install -g @openai/codex)"
    & npm.cmd install -g @openai/codex
    Refresh-Path
}
$results["Codex"] = if (Has "codex") { "OK ($(Version 'codex'))" } else { "설치 필요" }

# ---------------------------------------------------------------- 5. 결과 + 로그인
Step 5 "결과"
foreach ($k in $results.Keys) {
    $v = $results[$k]
    $c = if ($v -like "OK*") { "Green" } else { "Yellow" }
    Say ("  {0,-12} {1}" -f $k, $v) $c
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Has "claude") -or (Has "codex")) {
    Say ""
    Say "이제 로그인할까요? (각각 처음 한 번만, 크롬이 열려요)" Cyan
    if (Has "claude") {
        $a = Read-Host "  Claude Code 로그인 (Claude 유료 구독 계정) 할까요? [Y/n]"
        if ($a -eq "" -or $a -match "^[Yy]") { Start-Process -FilePath "$here\claude_login_chrome.bat" -WorkingDirectory $here }
    }
    if (Has "codex") {
        $a = Read-Host "  Codex 로그인 (ChatGPT 계정 - 개인 계정 추천) 할까요? [Y/n]"
        if ($a -eq "" -or $a -match "^[Yy]") { Start-Process -FilePath "$here\codex_login_chrome.bat" -WorkingDirectory $here }
    }
}

Say ""
Say "끝! 에이전트를 다시 켜고 '원클릭 준비 상태'에서 '다시 확인' -> 'Claude Code 테스트' / 'Codex 테스트'를 눌러보세요." Green
Say "노란색 항목이 있으면: 이 창을 닫고 install_ai_tools.bat 을 한 번 더 실행하면 대부분 해결돼요." Yellow
