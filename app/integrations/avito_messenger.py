"""Transport boundary: never pretend an unverified Avito operation succeeded."""
from typing import Protocol

class MessengerUnavailable(Exception):
    pass

class Messenger(Protocol):
    def send_text(self, account_id: str, chat_id: str, text: str) -> str: ...

class AvitoMessenger:
    def send_text(self, account_id: str, chat_id: str, text: str) -> str:
        raise MessengerUnavailable('Avito API contract and account permissions require verification')
