<#
注册 Windows 任务计划：每天定时运行体育新闻流水线，并把结果推送到手机（ntfy）。

用法（在项目目录下，用 PowerShell 运行）：
  .\scheduler.ps1                 # 用默认时间 08:00 注册
  .\scheduler.ps1 -Time "07:30"   # 指定每天几点
  .\scheduler.ps1 -Unregister     # 卸载任务
#>
param(
    [string]$Time = "08:00",
    [switch]$Unregister
)

$TaskName = "SportsNewsNtfy"
$Project  = $PSScriptRoot
$Python   = Join-Path $Project ".venv\Scripts\python.exe"
$Script   = Join-Path $Project "main.py"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已卸载任务：$TaskName"
    exit 0
}

if (-not (Test-Path $Python)) {
    Write-Host "错误：找不到 $Python，请先创建 .venv 并安装依赖。" -ForegroundColor Red
    exit 1
}

# 每天 $Time 触发一次，运行 python main.py --notify（工作目录固定为项目目录）
$Action    = New-ScheduledTaskAction -Execute $Python -Argument "--notify" -WorkingDirectory $Project
$Trigger   = New-ScheduledTaskTrigger -Daily -At $Time
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null

Write-Host "已注册任务：$TaskName"
Write-Host "  → 每天 $Time 运行：$Python $Script --notify"
Write-Host "  → 结果推送到 ntfy topic：zhenghz-sport（或 .env 里的 NTFY_TOPIC）"
Write-Host "  → 前提：到点电脑需开机且你已登录（任务以交互方式运行）"
Write-Host ""
Write-Host "查看/改时间：Get-ScheduledTask $TaskName | Get-ScheduledTaskInfo ；重跑本脚本即可改时间"
