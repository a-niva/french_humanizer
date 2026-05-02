@echo off
title Humanizer v2
cd /d "%~dp0"

REM --- Verifier Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python introuvable. Installez Python 3.10+ depuis https://python.org
    pause
    exit /b 1
)

REM --- Verifier Ollama ---
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Ollama introuvable. Installez Ollama depuis https://ollama.com
    pause
    exit /b 1
)

REM --- Creer le venv si absent (herite des packages systeme) ---
if not exist ".venv\Scripts\activate.bat" (
    echo Creation de l'environnement virtuel...
    python -m venv --system-site-packages .venv
)
call .venv\Scripts\activate.bat

REM --- Verifier les dependances ---
python -c "import gradio, ollama, pyperclip" >nul 2>&1
if %errorlevel% equ 0 goto :deps_ok

echo.
echo Installation des dependances manquantes...
pip install ollama pyperclip gradio
echo.

REM --- Re-verifier apres installation ---
python -c "import gradio, ollama, pyperclip" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] L'installation a echoue. Installez manuellement :
    echo   pip install ollama pyperclip gradio
    pause
    exit /b 1
)

:deps_ok

REM --- Verifier que le serveur Ollama tourne ---
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo Demarrage d'Ollama...
    start /min "" ollama serve
    timeout /t 3 /nobreak >nul
)

REM --- Lancer l'UI ---
echo.
echo ========================================
echo   Humanizer v2 - Demarrage...
echo   Interface : http://localhost:7860
echo   Ctrl+C pour quitter
echo ========================================
echo.
python ui.py

pause