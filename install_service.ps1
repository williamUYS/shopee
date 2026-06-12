# 财务对账工具 - 安装为 Windows 服务
# 请以管理员身份运行此脚本！

$nssm = "g:\财务工具\nssm\nssm.exe"
$pythonPath = "C:\Users\98297\AppData\Local\Programs\Python\Python313\python.exe"
$workDir = "g:\财务工具"

Write-Host "=== 财务对账工具 - Windows 服务安装 ===" -ForegroundColor Cyan

# 安装服务
Write-Host "[1/5] 安装服务..." -ForegroundColor Yellow
& $nssm install "财务对账工具" $pythonPath "-m uvicorn main:app --host 0.0.0.0 --port 3888"

# 设置工作目录
Write-Host "[2/5] 设置工作目录..." -ForegroundColor Yellow
& $nssm set "财务对账工具" AppDirectory $workDir

# 设置显示名称
Write-Host "[3/5] 设置显示名称..." -ForegroundColor Yellow
& $nssm set "财务对账工具" DisplayName "财务对账工具 Web 服务"

# 设置描述
Write-Host "[4/5] 设置描述..." -ForegroundColor Yellow
& $nssm set "财务对账工具" Description "库存管理与对账 Web 服务 (FastAPI + Uvicorn, Port 3888)"

# 设置开机自启
Write-Host "[5/5] 设置开机自启并启动..." -ForegroundColor Yellow
& $nssm set "财务对账工具" Start SERVICE_AUTO_START

# 启动服务
Write-Host "启动服务..." -ForegroundColor Yellow
& $nssm start "财务对账工具"

Write-Host ""
Write-Host "=== 安装完成！===" -ForegroundColor Green
Write-Host ""
Write-Host "服务名称: 财务对账工具" -ForegroundColor Cyan
Write-Host "端口: 3888" -ForegroundColor Cyan
Write-Host "访问地址: http://localhost:3888" -ForegroundColor Cyan
Write-Host ""
Write-Host "管理命令:" -ForegroundColor White
Write-Host "  查看状态: & `"$nssm`" status `"财务对账工具`""
Write-Host "  启动服务: & `"$nssm`" start  `"财务对账工具`""
Write-Host "  停止服务: & `"$nssm`" stop   `"财务对账工具`""
Write-Host "  卸载服务: & `"$nssm`" remove `"财务对账工具`" confirm"
Write-Host ""
Write-Host "或通过 services.msc 打开服务管理器查看" -ForegroundColor White
