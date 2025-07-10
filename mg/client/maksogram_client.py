from . message_methods import MessageMethods
from . account_methods import AccountMethods
from . modules_methods import ModulesMethods
from . database_methods import DatabaseMethods
from . background_methods import BackgroundMethods
from . user_updates_methods import UserUpdatesMethods
from . maksogram_base_client import MaksogramBaseClient
from . system_channels_methods import SystemChannelsMethods


class MaksogramClient(MaksogramBaseClient, MessageMethods, AccountMethods, DatabaseMethods,
                      BackgroundMethods, SystemChannelsMethods, UserUpdatesMethods, ModulesMethods):
    pass
