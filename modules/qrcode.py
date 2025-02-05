import qrcode
import time

from PIL import Image
from core import resources_path


def create(link: str) -> str:
    logo = Image.open(resources_path("logo.png"))
    logo = logo.convert("RGBA")
    width = 100
    logo = logo.resize((width, int((float(logo.size[1]) * float(width / float(logo.size[0]))))), 1)
    qr = qrcode.QRCode(version=6, error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(link)
    img = qr.make_image(fill_color="#e47c1b")
    img = img.convert("RGBA")
    pos = ((img.size[0] - logo.size[0]) // 2,
           (img.size[1] - logo.size[1]) // 2)
    img.paste(logo, pos, logo)
    file_path = resources_path(f"qr/{str(time.time())}.png")
    img.save(file_path, format="png")
    return file_path
