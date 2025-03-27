import os
import time

from moviepy import VideoFileClip

from typing import Union
from core import resources_path
from dataclasses import dataclass


@dataclass
class ResultConvertion:
    ok: bool
    path: Union[str, None]
    error: Union[Exception, None]


def convert(video_path: str) -> str:
    with VideoFileClip(video_path) as video:
        width, height = video.size
        if width > height:
            x1, x2 = (width - height) // 2, (width + height) // 2
            params = (x1, 0, x2, height)
        else:
            y1, y2 = (height - width) // 2, (height + width) // 2
            params = (0, y1, width, y2)

        with video.cropped(*params) as cropped_video:
            if cropped_video.w > 600:
                cropped_video = cropped_video.resized(height=600)
            file_path = resources_path(f"round_video/{int(time.time())}.mp4")
            cropped_video.write_videofile(file_path, codec='libx264', audio_codec='aac', logger=None)

    return file_path


def main(video_path: str) -> ResultConvertion:
    try:
        round_video_path = convert(video_path)
    except Exception as e:
        return ResultConvertion(ok=False, path=None, error=e)
    else:
        return ResultConvertion(ok=True, path=round_video_path, error=None)
    finally:
        os.remove(video_path)
