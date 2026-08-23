@echo off
echo ========================================
echo   QUANT DESK - 量化策略面板
echo ========================================
echo.
echo [1] 检查前端构建...
if not exist "server\static\index.html" (
    echo   未构建, 正在 npm run build...
    call npm run build
    if errorlevel 1 (
        echo   构建失败! 请先执行: npm install ^&^& npm run build
        pause
        exit /b 1
    )
) else (
    echo   已构建, 跳过
)
echo.
echo [2] 启动后端服务 (端口 8100)...
echo   浏览器打开 http://localhost:8100
echo   按 Ctrl+C 停止
echo.
python -m uvicorn server.main:app --host 0.0.0.0 --port 8100
pause
