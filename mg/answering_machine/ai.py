from mg.config import GIGACHAT_API_TOKEN

from hashlib import sha256
from logging import Logger
from typing import Optional
from uuid import UUID, uuid4

from mg.core.database import Database

from gigachat import GigaChat
from gigachat.context import session_id_cvar
from gigachat.api.post_chat import Chat, ChatCompletion
from gigachat.models.messages import Messages, MessagesRole


client = GigaChat(
    credentials=GIGACHAT_API_TOKEN,
    scope="GIGACHAT_API_PERS",
    model="GigaChat-2",
    verify_ssl_certs=False,
)
SYSTEM_MESSAGE = ("Ты - автоответчик в мессенджере, очень хорошо отвечающий на сообщения. "
                  "Тебе нужно от первого лица, как человек, ответить на входящее сообщение, учитывая пожелания пользователя\n\n"
                  
                  "Во входных данных будет JSON-строка с параметрами user_promt (пожелания пользователя - как нужно отвечать на входящее сообщение), "
                  "message (текст входящего сообщения, на которое нужно сгенерировать ответ) и meta_data (дополнительные данные о входящем сообщении "
                  "и его отправителе). Пример входных данных\n"
                  '{"user_promt": "Просто вежливо ответь на входящее сообщение. Скажи, что я сейчас занят",'
                  ' "message": "Привет. Ты сейчас свободен?",'
                  ' "meta_data": {"message_media": null, "sender": "Максим"}}\n\n'
                  
                  "Не отвечай слишком длинно (даже если попросил пользователь в user_promt) и используй контекст входящего сообщения и пожелания пользователя. "
                  "Отвечай по делу, без размышлений и воды. Расставляй знаки препинания и пиши по правилам русского языка "
                  "(если только иное не захотел пользователь в своем user_promt). В конце не нужно прощаться, предлагать написать еще раз или подобное\n\n"
                  
                  "В ответе укажи одно сообщение с ответом на входящее")


def generate_uuid4(account_id: int, answer_id: int) -> str:
    if not (account_id and answer_id):
        return uuid4().__str__()

    am_hash = sha256("answering_machine".encode()).digest()[:4]

    account_id_bytes = account_id.to_bytes(8, 'big', signed=True)
    answer_id_bytes = answer_id.to_bytes(4, 'big', signed=True)

    data = bytearray(am_hash + account_id_bytes + answer_id_bytes)
    data[6] = (data[6] & 0x0F) | 0x40  # Версия 4
    data[8] = (data[8] & 0x3F) | 0x80  # Вариант 10xx

    return UUID(bytes=bytes(data), version=4).__str__()


async def request(message: str, user_promt: str, meta_data: Optional[dict] = None, account_id: Optional[int] = None, answer_id: Optional[int] = None, logger: Optional[Logger] = None):
    """
    Запрос нейро-модели для ответа сообщение автоответчиком

    :param message: сообщение, на которое должен ответить автоответчик
    :param user_promt: подсказка нейро-модели от пользователя
    :param meta_data: дополнительная информация о сообщении и его отправителе
    :param account_id: необязательный параметр идентификатора клиента для кеширования ответов нейро-модели
    :param answer_id: необязательный параметр идентификатора автоответа для кеширования ответов нейро-модели
    :param logger: для логирования
    """

    client.get_token()
    session_id_cvar.set(generate_uuid4(account_id, answer_id))  # Идентификатор сессии на основе идентификатора автоответа для кеширования токенов


    input_data = {
        'user_promt': user_promt,
        'message': message,
        'meta_data': meta_data or {}
    }

    response: ChatCompletion = await client.achat(Chat(
        model="GigaChat-2",
        max_tokens=500,
        function_call="none",  # Генерация только текста без изображений, поиска в интернете и других функций
        messages=[
            Messages(
                role=MessagesRole.SYSTEM,
                content=SYSTEM_MESSAGE
            ),
            Messages(
                role=MessagesRole.USER,
                content=Database.serialize(input_data)
            ),
        ]
    ))

    if logger:
        logger.info(f"использовано {response.usage.total_tokens} токенов для генерации автоответа ({response.usage.__repr__()})")

    return response.choices[0].message.content
