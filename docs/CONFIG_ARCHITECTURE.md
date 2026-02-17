# Конфігурація AtlasTrinity

## Архітектура

AtlasTrinity використовує **гібридний підхід** до конфігурації:

```
┌─────────────────┐
│  Користувач     │
│  редагує .env   │ ◄─── Звичний інтерфейс
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  При старті     │
│  синхронізація  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  config.yaml            │
│  ~/.config/atlastrinity/│ ◄─── Система працює ТІЛЬКИ з цим
└─────────────────────────┘
```

### Чому так?

1. **Зручність для користувача**: `.env` файл - стандарт для API ключів
2. **Системність**: Один YAML конфіг зі всіма налаштуваннями
3. **Гнучкість**: Advanced users можуть редагувати `config.yaml` напряму
4. **Універсальність**: Працює однаково в dev та production

## Файли конфігурації

### `.env` (USER-FACING)

```bash
# Користувач редагує тут API ключі
COPILOT_API_KEY=your_key
GITHUB_TOKEN=your_token
COPILOT_MODEL=raptor-mini
VISION_MODEL=gpt-4o
```

**Розташування**:

- Dev: `/Users/.../atlastrinity/.env` (project root)
- Production: `~/.config/atlastrinity/.env`

### `config.yaml` (SYSTEM-FACING)

```yaml
# Система працює з цим файлом
api:
  copilot_api_key: 'your_key'
  github_token: 'your_token'

agents:
  atlas:
    model: 'raptor-mini'
    temperature: 0.7

  tetyana:
    model: 'gpt-4o'
    temperature: 0.5

  grisha:
    vision_model: 'gpt-4o'
    temperature: 0.3

mcp:
  terminal:
    enabled: true
    model: 'gpt-4o'

  filesystem:
    enabled: true
    model: 'gpt-4o'
```

**Розташування**: `~/.config/atlastrinity/config.yaml`

## Синхронізація

### Автоматична синхронізація (при кожному старті)

```python
# src/brain/server.py
from .config_sync import sync_env_to_config

# При старті FastAPI сервера
sync_env_to_config()
```

**Що відбувається**:

1. Читає `.env` з project root або `~/.config/`
2. Читає існуючий `config.yaml`
3. Оновлює `config.yaml` значеннями з `.env` (якщо відсутні)
4. Встановлює API ключі як environment variables

### Пріоритет

```
config.yaml > .env > defaults
```

**Приклад**: Якщо в `config.yaml` вказано `model: "gpt-4o"`, але в `.env` є `COPILOT_MODEL=raptor-mini`, то буде використано `gpt-4o`.

## Використання в коді

### Читання конфігурації

```python
from .config_loader import config

# Отримати налаштування агента
agent_config = config.get_agent_config("atlas")
model = agent_config.get("model", "raptor-mini")
temperature = agent_config.get("temperature", 0.7)

# Отримати налаштування MCP
mcp_config = config.get_mcp_config()
terminal_model = mcp_config.get("terminal", {}).get("model", "gpt-4o")

# Отримати налаштування безпеки
security = config.get_security_config()
dangerous_commands = security.get("dangerous_commands", [])

# Отримати довільне значення (dot notation)
max_depth = config.get("orchestrator.max_recursion_depth", 5)
```

### Отримання API ключів

```python
from .config_sync import get_api_key

copilot_key = get_api_key("copilot_api_key")
github_token = get_api_key("github_token")
```

## Workflow

### Development

```bash
# 1. Редагуєш .env в project root
vim .env

# 2. Запускаєш setup (один раз)
./scripts/setup.sh

# 3. Запускаєш dev сервер
npm run dev

# При старті:
# ✓ .env синхронізується в ~/.config/atlastrinity/config.yaml
# ✓ Система працює з config.yaml
```

### Production

```bash
# 1. Білдиш .app
npm run build:mac:custom

# 2. Користувач запускає AtlasTrinity.app

# При першому запуску:
# ✓ Resources/.env копіюється в ~/.config/atlastrinity/.env
# ✓ Resources/config.yaml копіюється в ~/.config/atlastrinity/config.yaml
# ✓ .env синхронізується в config.yaml
# ✓ Система працює з config.yaml
```

## Моделі

### Доступні моделі (Jan 2026)

| Модель           | ID                       | Краще для                              |
| ---------------- | ------------------------ | -------------------------------------- |
| Raptor mini      | `raptor-mini`            | Планування, reasoning                  |
| GPT-4.1          | `gpt-4o`                 | Виконання коду, швидкість              |
| GPT-4o           | `gpt-4o`                 | Vision, tool calling                   |
| GPT-5 mini       | `gpt-5-mini`             | Компактність                           |
| Grok Code Fast 1 | `grok-code-fast-1`       | Швидкий coding                         |
| Claude Haiku 4.5 | `claude-haiku-4.5`       | 🚀 Premium: 200K context, tool calling |
| Gemini Flash 3   | `gemini-flash-3-preview` | 🚀 Premium: 1M context (preview)       |

### Оптимальний розподіл

```yaml
agents:
  atlas:
    model: 'raptor-mini' # Планування потребує reasoning

  tetyana:
    model: 'gpt-4o' # Виконання - швидкість + якість

  grisha:
    vision_model: 'gpt-4o' # Vision обов'язково gpt-4o

mcp:
  terminal:
    model: 'gpt-4o' # Tool calling

  filesystem:
    model: 'gpt-4o' # Швидкість

  playwright:
    model: 'gpt-4o' # Browser automation

  computer_use:
    model: 'gpt-4o' # Vision-based control
```

## Міграція з попередньої версії

Якщо у вас вже є `.env` з `COPILOT_MODEL=gpt-4o`:

```bash
# 1. Система автоматично синхронізує при старті
npm run dev

# 2. Перевір config.yaml
cat ~/.config/atlastrinity/config.yaml

# 3. (Опціонально) Оновіть моделі вручну
vim ~/.config/atlastrinity/config.yaml
```

## Troubleshooting

### Проблема: API ключ не працює

```bash
# Перевір синхронізацію
cat ~/.config/atlastrinity/config.yaml | grep copilot_api_key

# Якщо немає - перевір .env
cat .env | grep COPILOT_API_KEY

# Примусова синхронізація
rm ~/.config/atlastrinity/config.yaml
npm run dev
```

### Проблема: Стара модель використовується

```bash
# config.yaml має пріоритет над .env
# Відредагуй config.yaml напряму:
vim ~/.config/atlastrinity/config.yaml

# Змінь:
agents:
  atlas:
    model: "raptor-mini"  # Замість старої моделі
```

### Проблема: Хочу повністю очистити конфіг

```bash
# Видали config.yaml
rm ~/.config/atlastrinity/config.yaml

# При наступному старті створить з defaults + .env
npm run dev
```

## Best Practices

1. **Для звичайних користувачів**: Редагуй тільки `.env`
2. **Для advanced users**: Редагуй `config.yaml` напряму
3. **Ніколи не зберігай** API ключі в git (`.env` в `.gitignore`)
4. **Використовуй `.env.example`** для шаблонів
5. **Перевіряй синхронізацію** після змін в `.env`
