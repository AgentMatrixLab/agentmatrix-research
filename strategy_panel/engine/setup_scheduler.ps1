# 每日 10:00 自动执行量化流水线
# 以管理员身份运行 PowerShell，执行此脚本

$taskName = "QUANT-DESK Daily Pipeline"
$scriptPath = "D:\bigquant\custom_engine\daily_pipeline.py"
$pythonPath = (Get-Command python).Source

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建新任务
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Daily -At "10:00"
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "QUANT DESK 每日数据更新+回测+部署流水线，每天10:00自动执行"

Write-Host "✅ 计划任务已创建: $taskName"
Write-Host "   执行文件: $pythonPath"
Write-Host "   脚本路径: $scriptPath"
Write-Host "   触发时间: 每天 10:00"

# 立即测试一次
Write-Host ""
Write-Host "是否立即执行一次测试？ (y/n)"
$confirm = Read-Host
if ($confirm -eq "y") {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "已触发执行，查看日志: D:\bigquant\custom_engine\daily_pipeline.log"
}
