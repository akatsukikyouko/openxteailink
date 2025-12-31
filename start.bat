@echo off
chcp 65001 >nul
echo ========================================
echo    XTEAILINK 互联启动器
echo ========================================
echo.

set UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

REM 检查uv是否安装
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到uv包管理器
    echo 请先安装uv: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

echo [信息] 检测到uv包管理器
echo.

REM 设置项目名称
set PROJECT_NAME=xteailink

REM 检查是否已在虚拟环境中
if defined VIRTUAL_ENV (
    echo [信息] 检测到虚拟环境: %VIRTUAL_ENV%
    echo.
) else (
    echo [信息] 创建虚拟环境...
    uv venv %PROJECT_NAME% --python 3.12 --clear
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境创建完成
    echo.
)

REM 激活虚拟环境
echo [信息] 激活虚拟环境...
call %PROJECT_NAME%\Scripts\activate
if %errorlevel% neq 0 (
    echo [错误] 激活虚拟环境失败
    pause
    exit /b 1
)
echo [成功] 虚拟环境已激活
echo.

REM 安装依赖
echo [信息] 检查并安装依赖...
uv pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)
echo [成功] 依赖安装完成
echo.

REM 检查配置文件
if not exist "config\config.json" (
    echo [警告] 配置文件config\config.json不存在，将使用默认配置
    echo.
)

REM 创建必要的目录
if not exist "data\pending_books" (
    echo [信息] 创建data\pending_books目录...
    mkdir data\pending_books
)

if not exist "logs" (
    echo [信息] 创建logs目录...
    mkdir logs
)

REM 启动Web服务器
echo [信息] 启动Web服务器...
echo [信息] 按Ctrl+C停止服务器
echo ========================================
echo.

python src\web_server.py

REM 如果服务器异常退出，保持窗口打开
echo.
echo [信息] 服务器已停止
pause
