from PIL import Image
from pathlib import Path
src = Path("assets/n_console_icon.png")
dst = Path("assets/n_console_icon.ico")
img = Image.open(src).convert("RGBA")
img.save(dst, format="ICO", sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
print(dst)
