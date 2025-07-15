from mg.config import WWW_SITE

from httpx import Timeout
from typing import Optional
from dataclasses import dataclass

from deepgram import (
    UrlSource,
    DeepgramClient,
    PrerecordedOptions,
    ClientOptionsFromEnv,
    AsyncListenRESTClient,
)


@dataclass
class ResultTranscription:
    ok: bool
    text: Optional[str]
    error: Optional[Exception]


api_options = ClientOptionsFromEnv()
options: PrerecordedOptions = PrerecordedOptions(
    model="nova-2",
    smart_format=True,
    language="ru-RU",
)


async def transcription(path: str) -> str:
    deepgram: AsyncListenRESTClient = DeepgramClient(config=api_options).listen.asyncrest.v("1")
    response = await deepgram.transcribe_url(UrlSource(url=f"{WWW_SITE}/{path}"), options, timeout=Timeout(120.0, connect=10.0))

    result = response['results']['channels'][0]['alternatives'][0]['transcript']
    return result


async def audio_transcription(path: str) -> ResultTranscription:
    try:
        text = await transcription(path)
    except Exception as e:
        return ResultTranscription(
            ok=False,
            text=None,
            error=e
        )
    else:
        return ResultTranscription(
            ok=True,
            text=text,
            error=None
        )
