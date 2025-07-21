import os
import sys


VERSION_GROUP = "3"
VERSION_ID = "3.0"
VERSION = "3.0.2 (148)"

release = sys.argv[1] == "release"
testing = len(sys.argv) > 2 and sys.argv[2] == "testing"

OWNER = int(os.environ['OWNER'])
FEE = int(os.environ['FEE'])
CHANNEL = os.environ['CHANNEL']
CHANNEL_ID = int(os.environ['CHANNEL_ID'])

TELEGRAM_BOT_API_TOKEN = os.environ['TELEGRAM_BOT_API_TOKEN']

TELEGRAM_API_ID = int(os.environ['TELEGRAM_API_ID'])
TELEGRAM_API_HASH = os.environ['TELEGRAM_API_HASH']

TELEGRAM_DC_ID = int(os.environ['TELEGRAM_DC_ID'])
TELEGRAM_DC_IP = os.environ['TELEGRAM_DC_IP']
TELEGRAM_DC_PORT = int(os.environ['TELEGRAM_DC_PORT'])

YOOMONEY_API_ID = int(os.environ['YOOMONEY_API_ID'])
YOOMONEY_API_KEY = os.environ['YOOMONEY_API_KEY']
CRYPTO_API_KEY = os.environ['CRYPTO_API_KEY']
OPENWEATHERMAP_API_KEY = os.environ['OPENWEATHERMAP_API_KEY']

NETANGELS_API_KEY = os.environ['NETANGELS_API_KEY']
MAKSOGRAM_PROCESS_ID = int(os.environ['MAKSOGRAM_PROCESS_ID'])
VIRTUALHOST_ID = int(os.environ['VIRTUALHOST_ID'])

db_config = {
    'host': os.environ['DBHOST'],
    'user': os.environ['DBUSER'],
    'password': os.environ['DBPASS'],
    'database': f'{os.environ['DBNAME']}_maksogram{VERSION_GROUP}'
}
email_config = {
    'host': os.environ['EMAIL_HOST'],
    'user': os.environ['EMAIL_USER'],
    'password': os.environ['EMAIL_PASSWORD']
}

if release:
    resources_path = "/home/c87813/tgmaksim.ru/Maksogram/resources"
    sessions_path = "/home/c87813/tgmaksim.ru/Maksogram/sessions"
    www_path = "/home/c87813/tgmaksim.ru/www/maksogram"
    log_path = "/home/c87813/tgmaksim.ru/Maksogram/log"

    SITE = "https://tgmaksim.ru/проекты/maksogram"
    WEB_APP = "https://tgmaksim.ru/maksogram"
    WWW_SITE = "https://tgmaksim.ru/maksogram"
    BLOG_SITE = "https://tgmaksim.ru/блог"
else:
    resources_path = "/home/c87813/debug.tgmaksim.ru/Maksogram/resources"
    sessions_path = "/home/c87813/debug.tgmaksim.ru/Maksogram/sessions"
    www_path = "/home/c87813/debug.tgmaksim.ru/www/maksogram"
    log_path = "/home/c87813/debug.tgmaksim.ru/Maksogram/log"

    SITE = "https://tgmaksim.ru/проекты/maksogram"
    WEB_APP = "https://tgmaksim.ru/maksogram"
    WWW_SITE = "https://debug.tgmaksim.ru/maksogram"
    BLOG_SITE = "https://tgmaksim.ru/блог"
