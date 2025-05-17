from typing import Union
from core import WWW_SITE
from httpx import Timeout
from dataclasses import dataclass
from deepgram import DeepgramClient, PrerecordedOptions, AsyncListenRESTClient, ClientOptionsFromEnv


@dataclass
class ResultTranscription:
    ok: bool
    text: Union[str, None]
    error: Union[Exception, None]


api_options = ClientOptionsFromEnv()
options: PrerecordedOptions = PrerecordedOptions(
    model="nova-3",
    smart_format=True,
    language="multi",
)


async def transcription(path: str) -> str:
    deepgram: AsyncListenRESTClient = DeepgramClient(config=api_options).listen.asyncrest.v("1")
    response = await deepgram.transcribe_url(dict(url=f"{WWW_SITE}/{path}"), options, timeout=Timeout(120.0, connect=10.0))
    result = response['results']['channels'][0]['alternatives'][0]['transcript']
    return result


async def main(path: str) -> ResultTranscription:
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
