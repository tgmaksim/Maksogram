import qrcode

from mg.core.functions import time_now, resources_path


def qr_code(link: str) -> str:
    qr = qrcode.make(link, version=4, error_correction=qrcode.constants.ERROR_CORRECT_H).get_image()
    file_path = resources_path(f"qr/{int(time_now().timestamp())}.jpg")
    qr.save(file_path)

    return file_path
