# Maakt assets/icon.png + assets/icon.ico voor DraveKookboek (eigen ontwerp: kookpan met stoom en een gouden lepel). Pillow nodig.
import os
from PIL import Image, ImageDraw

HIER = os.path.dirname(os.path.abspath(__file__))
N = 512
img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, N - 16, N - 16), radius=96, fill=(18, 20, 30, 255), outline=(111, 163, 214, 255), width=10)
# stoom: drie golvende lijnen
import math
for x in (196, 256, 316):
    pts = [(x + 14 * math.sin(t / 14.0), 210 - t) for t in range(0, 120, 4)]
    d.line(pts, fill=(200, 214, 230, 255), width=12, joint="curve")
# pan
d.rounded_rectangle((96, 250, 416, 420), radius=34, fill=(111, 163, 214, 255))
d.rectangle((80, 236, 432, 262), fill=(150, 190, 230, 255))
d.rounded_rectangle((36, 236, 96, 262), radius=10, fill=(90, 96, 120, 255))
d.rounded_rectangle((416, 236, 476, 262), radius=10, fill=(90, 96, 120, 255))
d.rounded_rectangle((120, 290, 392, 300), radius=4, fill=(150, 190, 230, 255))
# lepel
d.line([(330, 330), (440, 150)], fill=(255, 179, 71, 255), width=18)
d.ellipse((410, 108, 466, 176), fill=(255, 179, 71, 255))
os.makedirs(os.path.join(HIER, "assets"), exist_ok=True)
img.save(os.path.join(HIER, "assets", "icon.png"))
img.save(os.path.join(HIER, "assets", "icon.ico"), format="ICO",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icoon klaar")
