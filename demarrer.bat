@echo off
REM demarrer.bat - lance l'application sous Windows, d'un double-clic.
REM Installe les dependances au premier lancement, puis ouvre le navigateur.

cd /d "%~dp0"

where py >NUL 2>&1 && (set PY=py) || (set PY=python)
%PY% --version >NUL 2>&1 || (
  echo Python est introuvable. Installez-le depuis https://www.python.org/downloads/
  echo en cochant "Add Python to PATH", puis relancez ce fichier.
  pause
  exit /b 1
)

%PY% -c "import fastapi, uvicorn, pandas, plotly, openpyxl" 2>NUL || (
  echo Premier lancement : installation des dependances...
  %PY% -m pip install -r requirements.txt || (echo Installation impossible. & pause & exit /b 1)
)

start "" http://localhost:8000
echo Application demarree sur http://localhost:8000
echo Fermez cette fenetre pour l'arreter.
%PY% server.py
pause
