.ONESHELL
all:
	make install-reqs
	pip3 install pyinstaller --user
	python3 -m PyInstaller --name="SPO2 Viewer" --windowed --clean --onedir main.py
install-reqs:
	pip3 install -r requirements.txt --user
