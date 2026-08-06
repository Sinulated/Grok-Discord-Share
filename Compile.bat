pip install pyinstaller pillow

:: Create a multi-resolution .ico from your PNG (much more reliable for the title bar)
python -c "from PIL import Image; img=Image.open('512.png').convert('RGBA'); img.save('512.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

:: Build the EXE
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "Grok to WEBP" ^
  --icon=512.ico ^
  --add-data "512.ico;." ^
  --add-data "512.png;." ^
  --collect-all tkinterdnd2 ^
  --hidden-import=win11toast ^
  --hidden-import=dotenv ^
  --hidden-import=pyperclip ^
  --hidden-import=PIL ^
  app.py