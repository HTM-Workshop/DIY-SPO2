.ONESHELL:
all:
	make install-reqs
	pip3 install pyinstaller --user
	python3 -m PyInstaller --name="SPO2 Viewer" --windowed --icon=icon/icon.png --clean --onedir main.py
install-reqs:
	pip3 install -r requirements.txt --user
build-ui:
	pyuic5 spo2_window.ui > spo2_window.py
	pyuic5 license.ui > license.py
build-icon:
	pyrcc5 -o images_qr.py images.qrc
