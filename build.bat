@echo off
echo Compilando Recovery Pro...
pip install pyinstaller --quiet
pyinstaller --onefile --windowed --name=RecoveryPro --icon=icon.ico --add-data "licencias.py;." --add-data "recovery_engine.py;." --hidden-import=streamlit --collect-all streamlit main.py
echo Listo: dist\RecoveryPro.exe
pause
