' 财务对账工具 - 静默启动脚本
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""g:\财务工具\start_server.ps1""", 0, False
