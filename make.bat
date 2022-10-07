@echo off
pip3 install -r requirements.txt
pip3 install pyinstaller
pyinstaller --clean --window --name="SPO2 Viewer" --icon=icon/icon.png --onefile main.py
