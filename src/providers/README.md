# Providers Module

Централізований модуль для всіх LLM провайдерів AtlasTrinity.

## Структура

```
providers/
├── __init__.py              # Основний експорт модуля
├── __main__.py              # CLI інтерфейс
├── factory.py               # Фабрика провайдерів
├── copilot.py               # Copilot провайдер
├── windsurf.py              # Windsurf провайдер
├── utils/                   # Всі утиліти
│   ├── __init__.py
│   ├── switch_provider.py   # Перемикання провайдерів
│   ├── get_copilot_token.py # Токени Copilot
│   └── get_windsurf_token.py # Токени Windsurf
└── tests/                   # Тестові утиліти
    ├── __init__.py
    ├── test_windsurf_config.py
    └── quick_windsurf_test.py
```

## Швидкий старт

```bash
# 1. Отримати токен Copilot (ghu_) — автоматично оновлює `.env`
python -m providers token copilot --method vscode

# 2. Отримати токен Windsurf (sk-ws-)
python -m providers token windsurf

# 3. Перевірити токени
python -m providers token copilot --test
python -m providers token windsurf --test

# 4. Перемкнути провайдер
python -m providers switch windsurf
python -m providers status
```

---

## Архітектура

```
config.yaml → models.provider: "copilot" | "windsurf"
                     │
          providers/factory.py → create_llm()
               │                      │
         CopilotLLM              WindsurfLLM
      (ghu_ token)            (sk-ws- token)
      gpt-4o, gpt-4.1...      Free: swe-1.5, deepseek-r1, swe-1, grok-code-fast-1, kimi-k2.5...
               │                      │
      GitHub Copilot API       Proxy :8085 → Windsurf API
```

### Файли

| Файл                    | Опис                                                              |
| ----------------------- | ----------------------------------------------------------------- |
| `copilot.py`            | CopilotLLM — провайдер GitHub Copilot API                         |
| `windsurf.py`           | WindsurfLLM — провайдер Windsurf/Codeium API (тільки FREE моделі) |
| `factory.py`            | `create_llm()` — фабрика для автоматичного вибору провайдера      |
| `get_copilot_token.py`  | Скрипт отримання `ghu_` токена через OAuth Device Flow            |
| `get_windsurf_token.py` | Скрипт витягування `sk-ws-` токена з Windsurf DB                  |
| `__init__.py`           | Експорт: `CopilotLLM`, `WindsurfLLM`, `create_llm`                |

---

## Конфігурація

### config.yaml

```yaml
models:
  provider: 'copilot' # "copilot" або "windsurf"
  default: 'gpt-4o' # Модель за замовчуванням (для обраного провайдера)
```

### .env

**Важливо:** Скрипти (`get_copilot_token.py`, `get_windsurf_token.py`) пишуть токени
в **локальний** `.env` (корінь проєкту). Провайдери (`CopilotLLM`, `WindsurfLLM`)
читають з **глобального** `~/.config/atlastrinity/.env` через `config.py → load_dotenv()`.

```
Запис:  скрипти → ./env (локальний)
Читання: провайдери ← ~/.config/atlastrinity/.env (глобальний)
```

```bash
# === Copilot (GitHub) ===
COPILOT_API_KEY=ghu_...          # User-to-Server OAuth токен
VISION_API_KEY=ghu_...           # Для vision моделей (може = COPILOT_API_KEY)

# === Windsurf (Codeium) ===
WINDSURF_API_KEY=sk-ws-...       # API ключ Windsurf
WINDSURF_INSTALL_ID=uuid-...     # Installation ID з Windsurf DB
WINDSURF_MODEL=swe-1.5       # Модель за замовчуванням (FREE tier)

# === Override ===
LLM_PROVIDER=copilot             # Перевизначити провайдер через env
```

---

## Провайдер: GitHub Copilot

### Токен

| Поле           | Значення                                    |
| -------------- | ------------------------------------------- |
| **Тип**        | `ghu_` — User-to-Server OAuth Token         |
| **Видавець**   | GitHub Copilot App (`Iv1.b507a08c87ecfe98`) |
| **Отримання**  | OAuth Device Flow (браузер)                 |
| **Термін дії** | Не закінчується (поки активна підписка)     |
| **Зберігання** | `.env` → `COPILOT_API_KEY`                  |

### Типи GitHub токенів

| Префікс | Тип                               | Copilot API  |
| ------- | --------------------------------- | ------------ |
| `ghu_`  | User-to-Server (GitHub App OAuth) | ✅ Працює    |
| `ghp_`  | Personal Access Token             | ❌ Не працює |
| `gho_`  | OAuth App token (gh CLI)          | ❌ Не працює |
| `ghs_`  | Server-to-Server                  | ❌ Не працює |

### Доступні моделі (Copilot)

Copilot надає доступ до моделей через `api.githubcopilot.com`.
Множник показує витрату premium requests (0x = безкоштовно).

#### Copilot: Моделі та доступність

| Модель                     | Тип     | Доступність | Описання                                |
| -------------------------- | ------- | ----------- | --------------------------------------- |
| **gpt-4.1**                | Premium | ✅ Безкошні | Latest GPT-4 model (рекомендовано)      |
| **gpt-4o**                 | Premium | ✅ Безкошні | Multimodal, швидіння                    |
| **gpt-4o-mini**            | Premium | ✅ Безкошні | Швидіння, швидкий аналіз                |
| **gpt-5-mini**             | Premium | ✅ Безкошні | Новий GPT-5 модель                      |
| **grok-code-fast-1**       | Premium | ✅ Безкошні | Швидкий аналіз коду                     |
| **oswe-vscode-secondary**  | Premium | ✅ Безкошні | Raptor reasoning                        |
| **claude-haiku-4.5**       | Premium | ✅ Безкошні | 🚀 Claude Haiku 4.5 (200K context)      |
| **gemini-flash-3-preview** | Premium | ✅ Безкошні | 🚀 Gemini Flash 3 (1M context, preview) |
| **claude-3.5-sonnet**      | Premium | ✅ Безкошні | Аналітичний Claude                      |
| **o3-mini**                | Premium | ✅ Безкошні | Reasoning модель                        |
| **claude-4.5-opus**        | Premium | ❌ Платні   | Найкраща модель                         |

**Примітка:** Всі перелічені моделі доступні безкошно для GitHub Copilot токенів.
| GPT-5-Codex (Preview) | 1x | OpenAI |
| GPT-5.1 | 1x | OpenAI |
| GPT-5.1-Codex | 1x | OpenAI |
| GPT-5.1-Codex-Max | 1x | OpenAI |
| GPT-5.1-Codex-Mini (Preview) | 0.33x | OpenAI |
| GPT-5.2 | 1x | OpenAI |
| GPT-5.2-Codex | 1x | OpenAI |

> Повний список залежить від підписки. Перевірте: `python scripts/get_copilot_models.py`

### Отримання токена

```bash
# Інтерактивний режим
python -m providers.get_copilot_token

# OAuth Device Flow (найнадійніший) — за замовчуванням **авто-оновлює** `.env`
python -m providers.get_copilot_token --method vscode
# Щоб НЕ оновлювати `.env`, додайте прапорець:
python -m providers.get_copilot_token --method vscode --no-update-env

# Перевірити поточний токен
python -m providers.get_copilot_token --test

# Тихий режим (тільки токен)
python -m providers.get_copilot_token --method vscode --quiet
```

### Проксі (порт 8085) — Універсальний

```bash
python scripts/universal_proxy.py
# OpenAI-compatible: http://127.0.0.1:8085/v1/chat/completions
# Автоматично визначає провайдер за назвою моделі
```

**Автоматичне визначення провайдера:**

- `gpt-*`, `claude-*`, `o3-*` → Copilot
- `deepseek-*`, `swe-*`, `kimi-*` → Windsurf
- `X-Provider` header або `LLM_PROVIDER` env для примусового вибору

**VIBE проксі (спеціалізовані):**

```bash
python providers/proxy/copilot_vibe_proxy.py      # Copilot (порт 8086)
python providers/proxy/vibe_windsurf_proxy.py     # Windsurf (порт 8085)
```

---

## Провайдер: Windsurf (Codeium)

### Токен

| Поле           | Значення                                                             |
| -------------- | -------------------------------------------------------------------- |
| **Тип**        | `sk-ws-` — Windsurf API Key                                          |
| **Видавець**   | Codeium / Windsurf                                                   |
| **Отримання**  | Автоматично з Windsurf DB (`state.vscdb`)                            |
| **Зберігання** | `.env` → `WINDSURF_API_KEY`, `WINDSURF_INSTALL_ID`, `WINDSURF_MODEL` |

### Безкоштовні моделі (FREE tier)

WindsurfLLM дозволяє використовувати **тільки безкоштовні** моделі:

| Модель (для config)      | Windsurf ID                    | Опис                                     |
| ------------------------ | ------------------------------ | ---------------------------------------- |
| `swe-1.5`                | `MODEL_SWE_1_5`                | Windsurf SWE-1.5 — покращена версія      |
| `deepseek-r1`            | `MODEL_DEEPSEEK_R1`            | DeepSeek R1 (0528) — reasoning модель    |
| `swe-1`                  | `MODEL_SWE_1`                  | Windsurf SWE-1 — спеціалізована для коду |
| `grok-code-fast-1`       | `MODEL_GROK_CODE_FAST_1`       | xAI Grok Code Fast — швидкий кодинг      |
| `gpt-5.1-codex`          | `MODEL_PRIVATE_9`              | GPT-5.1-Codex — кодова модель            |
| `gpt-5.1-codex-mini`     | `MODEL_PRIVATE_19`             | GPT-5.1-Codex-Mini — легша версія        |
| `gpt-5.1-codex-max-low`  | `MODEL_GPT_5_1_CODEX_MAX_LOW`  | GPT-5.1-Codex Max (low reasoning)        |
| `gpt-5.1-codex-low`      | `MODEL_GPT_5_1_CODEX_LOW`      | GPT-5.1-Codex (low reasoning)            |
| `gpt-5.1-codex-mini-low` | `MODEL_GPT_5_1_CODEX_MINI_LOW` | GPT-5.1-Codex-Mini (low reasoning)       |
| `kimi-k2.5`              | `kimi-k2-5`                    | Kimi K2.5 — Moonshot AI                  |

### Value моделі (потребують кредити)

| Модель                     | Опис                      |
| -------------------------- | ------------------------- |
| SWE-1.5 (Promo)            | Промо-версія SWE-1.5      |
| GPT-5 (low reasoning)      | GPT-5 з низьким reasoning |
| GPT-5.1 (no/low reasoning) | GPT-5.1 базові варіанти   |
| Kimi K2                    | Moonshot AI K2            |
| Minimax M2 / M2.1          | Minimax моделі            |
| GLM 4.7                    | Zhipu AI GLM              |
| Qwen3-Coder                | Alibaba Qwen3 для коду    |
| xAI Grok-3 mini (Thinking) | Grok-3 mini з reasoning   |

### Premium моделі (потребують підписку)

| Модель                         | Провайдер |
| ------------------------------ | --------- |
| Claude Opus 4.5/4.6            | Anthropic |
| Claude Sonnet 4/4.5            | Anthropic |
| GPT-5.2 (all reasoning levels) | OpenAI    |
| GPT-4.1 / GPT-4o               | OpenAI    |
| Gemini 2.5 Pro / 3 Pro/Flash   | Google    |
| xAI Grok-3                     | xAI       |
| o3 (high reasoning)            | OpenAI    |

### Отримання токена

```bash
# Витягнути + автооновити .env
python -m providers.get_windsurf_token

# Тільки API key
python -m providers.get_windsurf_token --key-only

# Показати всі моделі
python -m providers.get_windsurf_token --models

# JSON вивід
python -m providers.get_windsurf_token --json

# Без оновлення .env
python -m providers.get_windsurf_token --no-update
```

### Проксі (через універсальний)

```bash
python scripts/universal_proxy.py
# OpenAI-compatible: http://127.0.0.1:8085/v1/chat/completions
# Автоматично маршрутизує Windsurf запити
# Список моделей:    http://127.0.0.1:8085/v1/models
```

**VIBE Windsurf проксі (порт 8085):**

```bash
python providers/proxy/vibe_windsurf_proxy.py --port 8085
```

---

## Інтеграція в код

### Використання фабрики (рекомендовано)

```python
from providers.factory import create_llm

# Автоматично обирає провайдер з config.yaml / LLM_PROVIDER
llm = create_llm(model_name="gpt-4o")

# Примусово Windsurf
llm = create_llm(model_name="swe-1.5", provider="windsurf")

# Примусово Copilot
llm = create_llm(model_name="gpt-4.1", provider="copilot")
```

### Пряме використання

```python
# Copilot
from providers.copilot import CopilotLLM
llm = CopilotLLM(model_name="gpt-4o")

# Windsurf
from providers.windsurf import WindsurfLLM
llm = WindsurfLLM(model_name="swe-1.5")
```

### LangChain інтерфейс

Обидва провайдери реалізують `BaseChatModel` і підтримують:

```python
# Синхронний виклик
result = llm.invoke([HumanMessage(content="Привіт")])

# Асинхронний виклик
result = await llm.ainvoke([HumanMessage(content="Привіт")])

# Streaming
msg = llm.invoke_with_stream(messages, on_delta=lambda chunk: print(chunk, end=""))

# Tool binding
llm_with_tools = llm.bind_tools([my_tool])
```

---

## Переключення провайдера

### Через config.yaml

```yaml
models:
  provider: 'windsurf' # Змінити на windsurf
  default: 'swe-1.5' # Використовувати free модель
```

### Через змінну середовища

```bash
export LLM_PROVIDER=windsurf
```

### Через код

```python
llm = create_llm(model_name="swe-1.5", provider="windsurf")
```

---

## Troubleshooting

### Copilot: 403 Forbidden

- **Причина:** Заблокований білінг або протермінована підписка
- **Рішення:** Оновіть підписку на GitHub, потім: `python -m providers.get_copilot_token --method vscode` (авто-оновлення `.env`)

### Copilot: 401 Unauthorized

- **Причина:** Токен протермінувався
- **Рішення:** `python -m providers.get_copilot_token --method vscode` (авто-оновлення `.env`)

### Copilot: 404 Not Found

- **Причина:** Неправильний тип токена (потрібен `ghu_`, не `gho_` чи `ghp_`)
- **Рішення:** Використовуйте OAuth Device Flow: `python -m providers.get_copilot_token --method vscode`

### Windsurf: resource_exhausted

- **Причина:** Rate limit або неправильний формат запиту
- **Рішення:** Використовуйте VIBE проксі: `python providers/proxy/vibe_windsurf_proxy.py`

### Windsurf: DB not found

- **Причина:** Windsurf не встановлено або не залогінено
- **Рішення:** Встановіть Windsurf і залогіньтесь хоча б раз

### WindsurfLLM: Model not in FREE tier

- **Причина:** Спроба використати premium модель
- **Рішення:** Використовуйте тільки free моделі (див. таблицю вище)
