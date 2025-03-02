import qrcode
import time

from core import resources_path


def create(link: str) -> str:
    qr = qrcode.make(link, version=4, error_correction=qrcode.constants.ERROR_CORRECT_H).get_image()
    file_path = resources_path(f"qr/{str(time.time())}.png")
    qr.save(file_path)
    return file_path
