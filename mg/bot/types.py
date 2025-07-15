from mg.config import release, TELEGRAM_BOT_API_TOKEN

from dataclasses import dataclass
from typing import Optional, Union

from aiogram import Bot, Dispatcher
from aiogram.client.telegram import TEST
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from telethon.tl.types import User, Chat, Channel


if release:
    bot = Bot(TELEGRAM_BOT_API_TOKEN, default=DefaultBotProperties(parse_mode="html"))
else:
    bot = Bot(TELEGRAM_BOT_API_TOKEN, session=AiohttpSession(api=TEST), default=DefaultBotProperties(parse_mode="html"))
dp = Dispatcher()


support = "tgmaksim_company"
support_link = f"<a href='tg://resolve?domain={support}'>тех. поддержке</a>"
feedback = "https://t.me/tgmaksim_ru/375?comment=510"
feedback_link = f"<a href='{feedback}'>отзывы</a>"
sticker_loading = "CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ" if release \
    else "BQACAgIAAxkBAAIBRGhW3GU9nd0l2-09-z327vAbHWU3AAIDAAPpnrlK5SagfnNms0Q2BA"


class Blocked:
    users = []  # Заблокированные админом пользователи


class Sleep:
    loading = True
    reload = False


class UserState(StatesGroup):
    class Admin(StatesGroup):
        mailing = State('mailing')
        confirm_mailing = State('confirm_mailing')
        login = State('login')

    phone_number = State('phone_number')
    code = State('code')
    password = State('password')
    relogin_code = State('relogin_code')
    relogin_password = State('relogin_password')

    city = State('city')
    time_zone = State('time_zone')
    add_chat = State('add_chat')
    remove_chat = State('remove_chat')

    new_changed_profile = State('new_changed_profile')

    speed_answer_trigger = State('speed_answer_trigger')
    speed_answer_text = State('speed_answer_text')

    security_email = State('security_email')
    confirm_email = State('confirm_email')
    new_security_agent = State('new_security_agent')

    ghost_stories = State('ghost_stories')
    ghost_copy = State('ghost_copy')

    new_status_user = State('new_status_user')

    main_currency = State('main_currency')
    my_currencies = State('my_currencies')

    auto_answer = State('auto_answer')
    edit_auto_answer_timetable = State('edit_auto_answer_timetable')
    edit_auto_answer_weekdays = State('edit_auto_answer_weekdays')
    auto_answer_trigger = State('auto_answer_trigger')
    auto_answer_chat = State('auto_answer_chat')

    edit_fire_name = State('edit_fire_name')


class CallbackDataParams(tuple):
    def get(self, index: int):
        """Безопасно обращается к i-элементу кортежа"""

        if index >= self.__len__():
            return None

        return self[index]


class CallbackData:
    @classmethod
    def __call__(cls, command: str, *params):
        """Создает callback_data с командой и необязательными дополнительными параметрами"""

        callback_data = command
        callback_data_params = []

        for param in params:
            if param is None:
                callback_data_params.append('n')
            elif param is True:
                callback_data_params.append('t')
            elif param is False:
                callback_data_params.append('f')
            elif isinstance(param, int):
                callback_data_params.append(f"i{param}")  # int
            elif isinstance(param, str):
                callback_data_params.append(f"s{param}")  # str
            else:
                callback_data_params.append(f"?{param}")  # Остальные типы

        return f"{callback_data}#{'|'.join(callback_data_params)}"

    @classmethod
    def deserialize(cls, callback_data: str) -> CallbackDataParams:
        """Десериализует callback_data в нужные параметры"""

        if callback_data.split("#", 1)[1] == '':  # Параметров нет
            return CallbackDataParams()

        callback_data_params = []

        for param in callback_data.split("#", 1)[1].split("|"):
            if param == 'n':
                callback_data_params.append(None)
            elif param == 't':
                callback_data_params.append(True)
            elif param == 'f':
                callback_data_params.append(False)
            elif param.startswith('i'):
                callback_data_params.append(int(param.removeprefix('i')))
            elif param.startswith('s'):
                callback_data_params.append(param.removeprefix('s'))
            else:
                callback_data_params.append(param.removeprefix('?'))

        return CallbackDataParams(callback_data_params)

    @classmethod
    def command(cls, command: str) -> str:
        """Название команды"""

        return f"{command}#"


class Subscription:
    def __init__(self, subscription_id: int, duration: int, discount: int, about: str):
        self.id = subscription_id
        self.duration = duration
        self.discount = discount
        self.about = about

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['Subscription']:
        return [cls.from_json(data) for data in json_data]

    @classmethod
    def from_json(cls, json_data: dict) -> 'Subscription':
        return cls(
            subscription_id=json_data['subscription_id'],
            duration=json_data['duration'],
            discount=json_data['discount'],
            about=json_data['about']
        )


@dataclass
class RequestUserResult:
    ok: bool
    user: Optional[User]
    warning: Optional[str]


@dataclass
class RequestChatResult:
    ok: bool
    chat: Optional[Union[Chat, Channel]]
    warning: Optional[str]
