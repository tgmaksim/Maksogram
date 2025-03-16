import os
import sys

from dotenv import load_dotenv


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

release = sys.argv[1] == "release"

RELEASE_TOKEN = os.environ["MaksogramBot"]  # Сохранение сообщений
DEBUG_TOKEN = os.environ["TestMaksimBot"]  # Тест бот
TOKEN = RELEASE_TOKEN if release else DEBUG_TOKEN

release_resources_path = lambda path: f"/home/c87813/tgmaksim.ru/Maksogram/resources/{path}"  # netangels
debug_resources_path = lambda path: f"resources/{path}"  # Локально
resources_path = release_resources_path if release else debug_resources_path

release_sessions_path = lambda phone: f"/home/c87813/tgmaksim.ru/Maksogram/sessions/{phone}.session"  # netangels
debug_sessions_path = lambda phone: f"sessions/{phone}.session"  # Локально
sessions_path = release_sessions_path if release else debug_sessions_path

RELEASE_BOT_ID = 7771336320
DEBUG_BOT_ID = 6332438420
BOT_ID = RELEASE_BOT_ID if release else DEBUG_BOT_ID

RELEASE_USERNAME_BOT = "MaksogramBot"
DEBUG_USERNAME_BOT = "TestMaksimBot"
USERNAME_BOT = RELEASE_USERNAME_BOT if release else DEBUG_USERNAME_BOT

db_config = {"host": os.environ['DBHOST'], "user": os.environ['DBUSER'],
             "password": os.environ['DBPASS'], "database": f"{os.environ['DBNAME']}_maksogram"}

openweathermap_api_key = os.environ['OPENWEATHERMAP_API_KEY']

email = {"host": os.environ['EMAIL_HOST'], "user": os.environ['EMAIL_USER'], "password": os.environ['EMAIL_PASSWORD']}
