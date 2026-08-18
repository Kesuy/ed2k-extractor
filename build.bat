@echo off
setlocal

where 7z >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\7-Zip\7z.exe" set "SEVENZIP=C:\Program Files\7-Zip\"
) else (
  for %%I in (7z.exe) do set "SEVENZIP=%%~dp$PATH:I"
)

if not defined SEVENZIP (
  echo [ERROR] 7-Zip not found. Install 7-Zip first.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --console ^
  --python-option "X utf8" ^
  --name ed2k-extractor ^
  --add-binary "%SEVENZIP%7z.exe;." ^
  --add-binary "%SEVENZIP%7z.dll;." ^
  ed2k_extractor.py

if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\ed2k-extractor.exe
endlocal
