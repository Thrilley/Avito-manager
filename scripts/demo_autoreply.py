"""Offline demonstration; temporary database, no API calls or real messages."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, SourceAccount, AvitoChat, AvitoReply
from app.integrations.gpt_replies import Draft
from app.services.avito_reply_service import ingest, generate

class DemoReplies:
    def generate(self, history):
        return Draft(reply='Здравствуйте! Чем могу помочь?', human_required=False)

def run():
    with tempfile.TemporaryDirectory() as folder:
        engine = create_engine(f'sqlite:///{Path(folder)/"demo.db"}')
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                user = User(username='demo', password_hash='not-a-real-login')
                db.add(user)
                db.flush()
                source = SourceAccount(owner_id=user.id, platform='avito', account_id='offline-demo')
                db.add(source)
                db.commit()
                event = SimpleNamespace(chat_id='demo-chat', message_id='hello', direction='in', text='Здравствуйте')
                first = ingest(db, user.id, source.id, event)
                chat = db.get(AvitoChat, first.chat_id)
                chat.enabled = True
                db.commit()
                reply = generate(db, user.id, first.id, DemoReplies())
                print('ТЕСТОВЫЙ РЕЖИМ: шаблонный ответ, без GPT и без отправки в Авито.')
                print('Покупатель:', event.text)
                print('Черновик:', reply.text)
                event.message_id, event.text = 'operator', 'Соедините с оператором'
                second = ingest(db, user.id, source.id, event)
                handoff = db.scalar(select(AvitoReply).where(AvitoReply.message_id == second.id))
                print('Покупатель:', event.text)
                print('Чат передан оператору:', handoff.status == 'human_required')
                print('Автоответчик приостановлен:', not chat.enabled)
        finally:
            engine.dispose()

if __name__ == '__main__':
    run()
