# 财务对账工具 - 启动脚本
$workDir = "g:\财务工具"
$logFile = "$workDir\server.log"

Set-Location $workDir

# 记录启动时间
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$timestamp] 服务启动"

# 启动 uvicorn
python -m uvicorn main:app --host 0.0.0.0 --port 3888 *>> $logFile
