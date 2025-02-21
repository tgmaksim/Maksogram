from typing import Union
from dataclasses import dataclass
from deepgram import DeepgramClient, ClientOptionsFromEnv, PrerecordedOptions, AsyncListenRESTClient


@dataclass
class ResultTranscription:
    ok: bool
    text: Union[str, None]
    error: Union[Exception, None]


deepgram: AsyncListenRESTClient = DeepgramClient(config=ClientOptionsFromEnv()).listen.asyncrest.v("1")
options: PrerecordedOptions = PrerecordedOptions(
    model="nova-2",  # Модель 2 версии с поддержкой нескольких языков
    smart_format=True,
    language="ru-RU"  # Только русский язык
)


async def transcription(data: bytes) -> str:
    response = await deepgram.transcribe_file(dict(buffer=data), options)
    result = response['results']['channels'][0]['alternatives'][0]['transcript']

    return result


async def main(data: bytes) -> ResultTranscription:
    try:
        text = await transcription(data)
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
