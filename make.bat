@echo off
pip3 install -r requirements.txt
pip3 install pyinstaller
pyinstaller --clean --window --name="SPO2 Viewer" --onefile --icon=icon/icon.png main.py
