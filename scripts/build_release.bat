@echo off
REM BubbleTrans 发布打包脚本：使用干净 .venv-release，避免脏依赖撑大体积
setlocal
cd /d "%~dp0.."

set VENV=.venv-release
set PY=%VENV%\Scripts\python.exe
set PI=%VENV%\Scripts\pyinstaller.exe

if not exist "%PY%" (
  echo [1/4] 创建干净打包虚拟环境 %VENV% ...
  py -3.11 -m venv %VENV% 2>nul || python -m venv %VENV%
  if errorlevel 1 (
    echo 创建 venv 失败，请确认已安装 Python 3.11+
    exit /b 1
  )
  echo [2/4] 安装正式依赖 ...
  "%PY%" -m pip install -U pip
  "%PY%" -m pip install -r requirements.txt pyinstaller
) else (
  echo [1/4] 复用已有 %VENV%
  echo [2/4] 同步正式依赖 ...
  "%PY%" -m pip install -r requirements.txt pyinstaller
)

echo [3/4] 清理旧构建 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] PyInstaller 打包 ...
"%PI%" BubbleTrans.spec
if errorlevel 1 (
  echo 打包失败
  exit /b 1
)

echo.
echo 完成: dist\BubbleTrans.exe
dir dist\BubbleTrans.exe
endlocal
