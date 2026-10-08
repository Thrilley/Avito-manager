# Публикация на GitHub

Репозиторий должен содержать исходники, тесты, документацию, migrations,
Dockerfile, compose.yaml и .env.example с безопасными примерами.
Не публикуйте .env, базы, backups, переписку, ключи и виртуальное окружение.

Перед публикацией:

```sh
python -m unittest discover -s tests -v
python -m scripts.demo_autoreply
git status --short
git diff --cached --stat
```

Откройте список подготовленных файлов и проверьте, что секретов и данных нет.
На GitHub создайте пустой репозиторий (например avito-manager), затем добавьте
его URL как origin и отправьте свой коммит. Пароли/токены не вставляйте в URL.
Не используйте принудительную отправку в существующий репозиторий.

Рекомендуемое описание:
«FastAPI backend for seller conversations, review-only AI drafts and operator
handoff. PostgreSQL, Alembic, Docker and isolated tests. Avito transport pending.»

Упомяните в описании портфолио, что реальные операции Avito пока отключены.
Лицензия не выбрана автоматически: перед открытым распространением определите,
какие права на использование кода хотите предоставить.
