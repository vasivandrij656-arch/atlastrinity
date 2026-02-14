# Автоматичний коміт та пуш бекапів баз даних

Ця функціональність автоматично комітить і пушить бекапи баз даних до GitHub після завершення фреш інсталу.

## Як це працює

1. **Створення бекапів**: Після завершення `setup_dev.py` створюються бекапи баз даних у `backups/databases/`
2. **Автоматичний коміт**: Скрипт `auto_commit_backups.sh` автоматично додає зміни до git
3. **Пуш до GitHub**: Зміни відправляються до віддаленого репозиторію

## Налаштування

### Автентифікація

Скрипт використовує GitHub токен з `.env` файлу:
```bash
GITHUB_TOKEN=your_token_here
```

### Вимкнення автоматичного коміту

Якщо потрібно вимкнути автоматичний коміт бекапів:

**Через командний рядок:**
```bash
python src/maintenance/setup_dev.py --no-auto-commit
```

**Через fresh_install:**
```bash
# Додайте прапорець --no-auto-commit до виклику setup_dev.py
# або відредагуйте скрипт вручну
```

## Скрипти

### `scripts/auto_commit_backups.sh`

Основний скрипт для автоматичного коміту та пушу:
- Перевіряє наявність змін у `backups/databases/`
- Використовує GitHub CLI або git з токеном
- Створює коміт з часовою міткою
- Пушить зміни до GitHub

### Інтеграція

**У `fresh_install.sh`:**
```bash
# Auto-commit and push database backups
echo ""
echo "🔄 Автоматичний коміт та пуш бекапів баз даних..."
if [ -f "scripts/auto_commit_backups.sh" ]; then
    bash "scripts/auto_commit_backups.sh"
else
    echo "⚠️ scripts/auto_commit_backups.sh не знайдено, пропускаємо коміт бекапів."
fi
```

**У `setup_dev.py`:**
```python
# Auto-commit and push backups to GitHub (unless disabled)
if not (args and hasattr(args, 'no_auto_commit') and args.no_auto_commit):
    print_info("Автоматичний коміт та пуш бекапів до GitHub...")
    # ... виклик auto_commit_backups.sh
```

## Переваги

- ✅ Автоматичне збереження бекапів у GitHub
- ✅ Відстеження історії змін баз даних
- ✅ Синхронізація між різними машинами
- ✅ Можливість вимкнути за потреби

## Вимоги

- GitHub CLI (`gh`) або git з токеном
- Наявний `GITHUB_TOKEN` у `.env`
- Права доступу до репозиторію
