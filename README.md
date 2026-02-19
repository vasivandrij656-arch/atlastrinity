# AtlasTrinity 🔱

**Autonomous Recursive Agentic System for macOS**
_High-End AGI-lite Architecture (Thin Client, Fat Brain)_

[![CI Core Pipeline](https://github.com/olegkizima01/atlastrinity/workflows/CI%20Core%20Pipeline/badge.svg)](https://github.com/olegkizima01/atlastrinity/actions/workflows/ci-core.yml)
[![Trinity Agent Tests](https://github.com/olegkizima01/atlastrinity/workflows/Trinity%20Agent%20Tests/badge.svg)](https://github.com/olegkizima01/atlastrinity/actions/workflows/test-trinity.yml)

![AtlasTrinity UI](design-system/dizaine_electron.png)

### 💎 Код Вищої Проби (Strict Integrity)

Весь когнітивний стек (Brain + 18 MCP серверів) пройшов глибоке загартування. Провірено: **0 помилок** у типах, асинхронних викликах та структурі через Pyrefly. Вся взаємодія з Redis модернізована до `redis.asyncio`.

---

## 🌟 Про Проєкт

**AtlasTrinity** — це інтелектуальна мультиагентна екосистема для macOS, що дозволяє автономно виконувати будь-які задачі на комп'ютері через голос або текст. Система використовує тріаду агентів (**Атлас**, **Тетяна**, **Гріша**) для планування, виконання та верифікації дій за допомогою протоколу MCP (Model Context Protocol).

### Що робить AtlasTrinity унікальним:

- 🧠 **Recursive Multi-Agent Intelligence** — три агенти з різними ролями, що рекурсивно вирішують задачі будь-якої глибини
- 🔧 **173+ інструментів** через єдиний MCP hub (XcodeBuild + macOS-use + GoogleMaps + Windsurf)
- 🔄 **Self-Healing Engine** — автоматичне виправлення помилок через CI-Bridge та Hypermodule
- 🗣️ **Голосовий інтерфейс** — розпізнавання (Whisper large-v3) та синтез мовлення (українські голоси)
- 🗺️ **Кібер-панк карти** — інтерактивні Google Maps з віртуальними турами та Street View
- 💾 **Багаторівнева пам'ять** — SQLite + ChromaDB + Redis + Golden Fund з семантичним пошуком
- 🔐 **Автентифікація** — OAuth2, Keychain, Credential Vault, Дія.EЦП, BankID
- 🖥️ **Electron Desktop App** — Vite + React інтерфейс з real-time дашбордом агентів
- 📊 **Data Analysis** — Pandas-based аналіз даних (CSV, Excel, JSON, Parquet)
- 🔀 **Hybrid LLM Providers** — автоматичне перемикання між Copilot і Windsurf

---

## 📋 Системні Вимоги

| Компонент   | Мінімум        | Рекомендовано       |
| ----------- | -------------- | ------------------- |
| **macOS**   | 14.5+ (Sonoma) | 15.0+ (Sequoia)     |
| **Python**  | 3.10+          | 3.12.12             |
| **Node.js** | 18.x           | 22.x+               |
| **Swift**   | 5.9+           | 6.x                 |
| **Redis**   | 7.x            | latest              |
| **Bun**     | 1.x            | latest              |
| **Xcode**   | 16.x+          | latest              |
| **Disk**    | ~5 GB          | ~10 GB (з моделями) |

---

## 🚀 Швидкий Старт

### 1. Клонування та налаштування

```bash
# Клонуйте репозиторій
git clone https://github.com/olegkizima01/atlastrinity.git
cd atlastrinity

# Повне автоматичне розгортання
npm run setup
# або
python3 scripts/setup_dev.py
```

### 2. Що робить Setup:

- ✅ **Python venv**: Створює `.venv` з усіма залежностями з `requirements.txt`
- ✅ **NPM пакети**: Встановлює 18+ MCP серверів (Swift, Python, Node)
- ✅ **FORCED Native Build**: Перекомпілює Swift MCP сервери (`macos-use`, `googlemaps`, `windsurf`) для гарантованої роботи
- ✅ **AI Models**: Завантажує TTS (український голос) та STT (Faster-Whisper large-v3) моделі (~3 GB)
- ✅ **Redis**: Встановлює через Homebrew і запускає сервіс
- ✅ **FORCED Config Sync**: Синхронізує конфігурації з примусовим перезаписом `~/.config/atlastrinity/` з актуальних темплейтів
- ✅ **SQLite DB**: Ініціалізує базу даних (таблиця `recovery_attempts`, сесії, таски)
- ✅ **Dev Tools**: Встановлює Ruff, Pyrefly, Oxlint, Knip, MCP Inspector
- ✅ **Перевіряє**: Python версію, наявність Swift, Bun, Redis, Vibe CLI

### 3. Налаштування API ключів

```bash
# Відредагуйте ~/.config/atlastrinity/.env
nano ~/.config/atlastrinity/.env
```

```env
# === Copilot (основний провайдер) ===
COPILOT_API_KEY=ghu_your_token_here

# === Windsurf (альтернативний провайдер) ===
WINDSURF_API_KEY=sk-ws-your_token_here
WINDSURF_INSTALL_ID=your_install_id_here

# === GitHub (для GitHub MCP сервера) ===
GITHUB_TOKEN=ghp_your_token_here

# === Google Maps (для навігації та карт) ===
GOOGLE_MAPS_API_KEY=your_key_here
```

### 4. Запуск

```bash
npm run dev
```

Одна команда запускає **5 паралельних процесів**:

| Процес             | Опис                        | URL                     |
| ------------------ | --------------------------- | ----------------------- |
| **Brain**          | Python FastAPI backend      | `http://127.0.0.1:8000` |
| **Renderer**       | Vite React frontend         | `http://localhost:3000` |
| **Electron**       | Desktop window              | —                       |
| **Copilot Proxy**  | LLM API шлюз                | `:8086`                 |
| **Config Watcher** | Авто-синхронізація конфігів | —                       |

### 5. Перевірка системи

```bash
# Стан MCP серверів (90+ інструментів)
npm run mcp:status

# Перевірка середовища
npm run verify

# Перевірка Redis
npm run redis:check

# Цілісність коду
npm run lint:all
```

### Fresh Install (з нуля)

Для повного чистого встановлення (видаляє кеші та починає з нуля):

```bash
npm run fresh-install
```

---

## 🤖 Когнітивна Архітектура (Trinity)

Система використовує **Multi-Agent Reasoning Loop**, де кожен агент має свою спеціалізацію:

| Агент         | Роль                                 | Модель (default)          | Голос   |
| ------------- | ------------------------------------ | ------------------------- | ------- |
| **Атлас** 🔱  | Стратег (Мета-Планувальник)          | gpt-4.1                   | Dmytro  |
| **Тетяна** ⚡ | Виконавець (Tools / CLI / GUI)       | gpt-4.1                   | Tetiana |
| **Гріша** 🛡️  | Критик (Vision / Security / Testing) | gpt-4.1 + gpt-4o (Vision) | Mykyta  |

### Як працює цикл:

```
Запит користувача
      │
      ▼
┌─ ATLAS (Стратег) ──────────────────────┐
│  • Аналіз запиту + пошук у ChromaDB    │
│  • Мета-планування (Sequential Thinking)│
│  • Створення покрокового плану          │
└──────────────┬─────────────────────────┘
               │
      ┌────────▼────────┐
      │  TETYANA (Exec)  │◄── Feedback від Гріші
      │  • Виконання    │     (рекомендації, звіти)
      │    через MCP    │
      └────────┬────────┘
               │
      ┌────────▼────────┐
      │  GRISHA (Audit)  │
      │  • Vision аналіз │     ✅ → Продовжуємо
      │  • Security check │     ❌ → Рекурсивне виправлення
      │  • Quality Score  │
      └─────────────────┘
```

- **Recursive Self-Correction**: Якщо крок провалюється, Атлас створює підзадачу, яка виконується за тими самими правилами — глибина рекурсії до 5 рівнів
- **Strategic Deviation**: Тетяна може запропонувати ефективніший шлях — Атлас оцінює і перебудовує план "на льоту"
- **Vision-Based Verification**: Гріша робить скріншоти, аналізує через GPT-4o Vision, підтверджуючи фактичне виконання

---

## 🔀 Hybrid LLM Providers

AtlasTrinity підтримує **два LLM провайдери** з автоматичним перемиканням:

### GitHub Copilot (Primary)

| Модель                   | Призначення                     |
| ------------------------ | ------------------------------- |
| `gpt-4.1`                | Основна модель для всіх агентів |
| `gpt-4o`                 | Vision / Multimodal задачі      |
| `gpt-5-mini`             | Швидкі задачі                   |
| `claude-haiku-4.5`       | Claude 4.5 (200K context)       |
| `gemini-flash-3-preview` | Gemini Flash 3 (1M context)     |
| `oswe-vscode-secondary`  | Deep problem analysis           |
| `o3-mini`                | Reasoning модель                |

### Windsurf / Codeium (Alternative, FREE tier)

| Модель          | Призначення                     |
| --------------- | ------------------------------- |
| `swe-1.5`       | Software engineering specialist |
| `deepseek-r1`   | Logical reasoning & CoT         |
| `kimi-k2.5`     | Fast context & coding           |
| `gpt-5.1-codex` | GPT-5.1 Codex                   |

```bash
# Перемикання провайдера
python -m providers switch windsurf

# Перевірка стану
python -m providers status

# Отримання токенів
python -m providers token copilot --method vscode
python -m providers token windsurf
```

Формат **Hybrid Configuration** (per-model override):

```yaml
models:
  provider: 'copilot'
  default: 'copilot:gpt-4.1'
  vision: 'copilot:gpt-4o'
  reasoning: 'copilot:gpt-4.1'
  # Можна поєднувати провайдери:
  # reasoning: "windsurf:deepseek-r1"
```

---

## 🛠 Екосистема MCP (18 Активних Серверів, 200+ Інструментів)

MCP (Model Context Protocol) — це "нервова система" AtlasTrinity. Сервери організовані за тірами:

### Tier 1 — Ядро Системи

| Сервер                  | Інструментів | Технологія             | Опис                                                                     |
| ----------------------- | ------------ | ---------------------- | ------------------------------------------------------------------------ |
| **xcodebuild**          | **173+**     | Node.js + Swift Bridge | Єдиний хаб: Xcode (94) + macOS-use (63) + GoogleMaps (11) + Windsurf (5) |
| **windsurf**            | 16           | Native Swift           | Windsurf AI з Cascade Action Phase                                       |
| **filesystem**          | 11           | Node.js                | Файлові операції (read/write/search/move)                                |
| **sequential-thinking** | 1            | Node.js (Bun)          | Динамічне покрокове планування                                           |

### Tier 2 — Високий Пріоритет

| Сервер                | Інструментів | Технологія                 | Опис                                                                 |
| --------------------- | ------------ | -------------------------- | -------------------------------------------------------------------- |
| **vibe**              | 18           | Python                     | AI Coding, Self-Healing, Code Review, Debugging                      |
| **memory**            | 9            | Python (SQLite + ChromaDB) | Knowledge Graph, persistent memory                                   |
| **golden-fund**       | 8            | Python                     | Золотий фонд знань: semantic search, entity probing, data analysis   |
| **graph**             | 4            | Python                     | Візуалізація Knowledge Graph (Mermaid, JSON)                         |
| **data-analysis**     | 10           | Python (Pandas)            | Аналіз даних: CSV, Excel, JSON, Parquet                              |
| **devtools**          | 7+           | Python                     | Linter wrapper (Ruff, Oxlint, Knip, Pyrefly), MCP Inspector, Sandbox |
| **redis**             | 5            | Python                     | State inspection: get/set/keys/delete/info                           |
| **duckduckgo-search** | 3            | Python                     | Швидкий веб-пошук без API ключів                                     |
| **whisper-stt**       | 2            | Python (Whisper)           | Speech-to-Text (Faster-Whisper large-v3)                             |
| **github**            | 20+          | Node.js                    | GitHub API: PRs, Issues, Search, File Operations                     |
| **tour-guide**        | 6            | Python (Internal)          | Віртуальні тури: start/stop/pause/resume/look/speed                  |

### Tier 3 — Додаткові

| Сервер             | Технологія | Опис                                           |
| ------------------ | ---------- | ---------------------------------------------- |
| **puppeteer**      | Node.js    | Headless browser automation (Puppeteer)        |
| **context7**       | Node.js    | Context-aware documentation для бібліотек      |
| **react-devtools** | Node.js    | React introspection (Fiber tree, Props, State) |

### Tier 4 — Спеціалізовані

| Сервер              | Технологія    | Опис                                           |
| ------------------- | ------------- | ---------------------------------------------- |
| **chrome-devtools** | Node.js (Bun) | Chrome DevTools Protocol, browser debugging    |
| **postgres**        | Python        | PostgreSQL (experimental, disabled by default) |

> **XcodeBuild Hub** — єдина точка входу для 4 Swift бекендів: `macos-use` (GUI automation, Vision/OCR, Terminal, Calendar, Notes, Mail, Finder), `googlemaps` (geocode, directions, street view, places), `windsurf` (chat, cascade), та 94 нативні Xcode інструменти (Build, Test, Simulators).

---

## 🖥️ Electron Desktop App

Інтерфейс побудований на **Electron + Vite + React** (TypeScript):

| Компонент               | Призначення                                                 |
| ----------------------- | ----------------------------------------------------------- |
| **NeuralCore**          | Центральна панель з clockwork-анімацією стану агентів       |
| **ChatPanel**           | Текстовий діалог з агентами                                 |
| **CommandLine**         | Прямий ввід команд для MCP серверів                         |
| **MapView**             | Інтерактивна Google Maps з кібер-панк стилем та Street View |
| **AgentStatus**         | Real-time статус кожного агента (Atlas, Tetyana, Grisha)    |
| **ExecutionLog**        | Живий лог виконання кроків                                  |
| **SessionManager**      | Управління сесіями та історією                              |
| **ClockworkBackground** | Animated clockwork mechanism за agent layers                |

**Комунікація**: Redis Pub/Sub забезпечує миттєве оновлення UI при кожній дії агентів.

---

## 🎙️ Голосовий Інтерфейс (Voice)

| Функція       | Технологія              | Деталі                                                   |
| ------------- | ----------------------- | -------------------------------------------------------- |
| **STT**       | Faster-Whisper large-v3 | Локальна модель, українська/англійська                   |
| **TTS**       | Ukrainian-TTS           | Голоси: Dmytro (Атлас), Tetiana (Тетяна), Mykyta (Гріша) |
| **Bilingual** | Auto-detect             | Автоматичне визначення мови                              |

---

## 🔄 Self-Healing & Monitoring

### Self-Healing Engine (`src/brain/healing/`)

| Модуль                 | Призначення                                      |
| ---------------------- | ------------------------------------------------ |
| **Hypermodule**        | Рекурсивний аналіз та виправлення помилок        |
| **CI Bridge**          | Інтеграція з CI/CD для автоматичного виправлення |
| **Parallel Healing**   | Паралельне виправлення кількох проблем           |
| **System Healing**     | Відновлення системного стану після збоїв         |
| **Server Manager**     | Перезапуск MCP серверів при втраті зв'язку       |
| **Improvement Engine** | Аналіз патернів помилок та генерація покращень   |
| **Log Analyzer**       | Структурований аналіз логів для діагностики      |

### Monitoring (`src/brain/monitoring/`)

- **Watchdog**: Моніторинг здоров'я системи з автоматичними alert-ами
- **Metrics**: Prometheus-compatible метрики (порт 8001)
- **Notifications**: Системні нотифікації при критичних подіях
- **OpenTelemetry**: Tracing для всіх MCP викликів

---

## 💾 Система Пам'яті (Memory Hierarchy)

| Рівень              | Технологія              | Призначення                                                       |
| ------------------- | ----------------------- | ----------------------------------------------------------------- |
| **Короткострокова** | Redis + `SharedContext` | Поточний стан: відкриті файли, CWD, активні операції              |
| **Структурована**   | SQLite (aiosqlite)      | Історія сесій, тасків, GraphChain, логів                          |
| **Семантична**      | ChromaDB (Vector Store) | "Досвід" — абстрактні стратегії та уроки для пошуку за подібністю |
| **Golden Fund**     | Dedicated MCP Server    | Верифіковані знання з примусовою ізоляцією та системою "Промоції" |

### Golden Fund Workflow

1. Нові дані потрапляють в ізольований **Sandbox Namespace**
2. Після успішної верифікації Грішою (Quality Score > 0.7) — **Promotion** до глобального фонду
3. **Semantic Chaining** — автоматичний пошук зв'язків між датасетами
4. **Data Chain Tracing** — реконструкція цілісних записів з фрагментованих джерел

---

## 📊 Data Analysis Engine

Pandas-based сервер для аналізу даних (`data-analysis` MCP):

- **Формати**: CSV, Excel, JSON, Parquet
- **Інструменти**: `read_metadata`, `analyze_dataset`, `generate_statistics`, `create_visualization`, `data_cleaning`, `data_aggregation`, `interpret_column_data`, `run_pandas_code`
- Інтеграція з Golden Fund для зберігання результатів аналізу

---

## 🗺️ Навігація та Віртуальні Тури

- **Google Maps Integration** (11 інструментів): geocoding, directions, traffic, places search, street view
- **Tour Driver** (`src/brain/navigation/`): Автономні віртуальні тури з реальним переміщенням по карті
- **Tour Guide** (Internal MCP): `tour_start`, `tour_stop`, `tour_pause`, `tour_resume`, `tour_look`, `tour_set_speed`
- **MapView** UI: Кібер-панк стилізація з ефектами, POI маркерами та Street View

---

## 🔐 Автентифікація та Безпека

### Credential Management

- **Credential Vault** — зашифроване локальне сховище із підтримкою auto-refresh
- **macOS Keychain** — інтеграція з системним сховищем
- **SSH/GPG Agent** — підтримка SSH та GPG ключів
- **Auto-Discovery** — автоматичне сканування credential stores

### Identity Providers (підготовлено)

- **Дія.ЕЦП** — електронний цифровий підпис
- **BankID** — банківська ідентифікація
- **NFC** — біометричні паспорти / ID карти
- **X.509 / PKCS#12** — сертифікати

### Security Guardrails

- **Command Blocklist** — заборонені деструктивні команди (`rm -rf`, `mkfs`, `dd`)
- **Grisha Security Audit** — кожен крок проходить аудит безпеки
- **Detect-Secrets** — автоматичне сканування на витік секретів
- **Safety Check** — перевірка Python залежностей на вразливості

---

## ⚙️ Розумна Конфігурація (Global First)

AtlasTrinity використовує архітектуру **Global First** для безпеки та зручності:

| Шлях                             | Призначення                                              |
| -------------------------------- | -------------------------------------------------------- |
| `config/*.template`              | **Source of Truth** — шаблони конфігурацій у репозиторії |
| `~/.config/atlastrinity/`        | **Runtime** — активні конфігурації (авто-синхронізація)  |
| `~/.config/atlastrinity/.env`    | **Secrets** — API ключі та токени                        |
| `~/.config/atlastrinity/models/` | **AI Models** — локальні STT/TTS моделі                  |

```bash
# Синхронізація конфігурацій
npm run config:sync

# Стан синхронізації
python3 config/config_sync.py status

# Auto-watch (запускається разом з npm run dev)
npm run watch:config
```

---

## 📈 CI/CD Pipeline

### GitHub Actions Workflows

| Workflow                | Тригер   | Що робить                                                                               |
| ----------------------- | -------- | --------------------------------------------------------------------------------------- |
| **CI Core Pipeline**    | Push, PR | Лінтинг (Biome, Oxlint, TSC, ESLint, Ruff, Pyright, Pyrefly), тести з покриттям, збірка |
| **Trinity Agent Tests** | Push, PR | Тестування агентів Atlas, Tetyana, Grisha, MCP оркестрація                              |

### Dependabot

Автоматичне оновлення залежностей: npm, pip, GitHub Actions.

### Локальний запуск

```bash
# Встановити залежності
npm ci
pip install -r requirements.txt

# Лінтинг (8 linters за один запуск)
npm run lint:all

# Тести з покриттям
npm run test:ci

# Збірка
npm run build:ci

# Форматування коду
npm run format:write
```

---

## 📦 Production Build

Для створення готового macOS додатку (.app / .dmg):

```bash
# Повна збірка DMG (arm64)
npm run build:mac

# Тільки DMG
npm run build:dmg

# Custom збірка
npm run build:mac:custom
```

**Що входить у збірку:**

- Electron app з bundled Vite React UI
- Python Brain (FastAPI) з venv
- Всі MCP сервери (Swift бінарники + Python + Node)
- Конфігурації та моделі

---

## 🗂️ Структура Проекту

```text
atlastrinity/
├── src/
│   ├── brain/                # 🧠 Python Core (FastAPI, Asyncio)
│   │   ├── agents/           #    Atlas, Tetyana, Grisha implementations
│   │   ├── auth/             #    OAuth2, Keychain, Vault, Credential Engine
│   │   ├── behavior/         #    Поведінкові конфігурації агентів
│   │   ├── core/             #    Orchestrator, SharedContext, StateManager
│   │   ├── data/             #    Database Manager, Models, Migrations
│   │   ├── healing/          #    Self-Healing: Hypermodule, CI Bridge, Parallel
│   │   ├── memory/           #    ChromaDB, Golden Fund, Semantic Search
│   │   ├── mcp/              #    MCP Client, Tool Dispatcher, Routing
│   │   ├── monitoring/       #    Watchdog, Metrics, Notifications, Tracing
│   │   ├── navigation/       #    Tour Driver, Map State, Virtual Tours
│   │   ├── prompts/          #    Agent Intelligence Protocols
│   │   ├── voice/            #    STT (Whisper), TTS (Ukrainian-TTS)
│   │   └── server.py         #    Main API Gateway
│   ├── main/                 # ⚡ Electron Host Process (TypeScript)
│   ├── renderer/             # 🎨 Frontend UI (React + Vite + TypeScript)
│   │   ├── components/       #    NeuralCore, ChatPanel, MapView, CommandLine...
│   │   └── styles/           #    Vanilla CSS design system
│   ├── mcp_server/           # 🔧 Custom MCP Servers (Python)
│   │   ├── vibe_server.py    #    AI Coding & Self-Healing (18 tools)
│   │   ├── memory_server.py  #    Knowledge Graph (9 tools)
│   │   ├── golden_fund/      #    Verified Knowledge Base (8 tools)
│   │   ├── data_analysis_server.py  # Pandas Data Analysis (10 tools)
│   │   ├── devtools_server.py       # Dev Tools & Linter Wrapper
│   │   ├── duckduckgo_search_server.py  # Web Search
│   │   ├── graph_server.py   #    Knowledge Graph Visualization
│   │   ├── redis_server.py   #    Redis State Inspection
│   │   └── whisper_server.py #    Speech-to-Text
│   ├── providers/            # 🔀 LLM Providers (Copilot, Windsurf, Proxy)
│   ├── integrations/         # 🔗 XcodeBuild MCP Integration
│   └── maintenance/          # 🔧 Setup, Health, Config Sync, Cleanup
├── vendor/                   # 📦 External Swift MCP servers
│   ├── XcodeBuildMCP/        #    Unified hub (173+ tools)
│   ├── mcp-server-macos-use/ #    macOS automation (63 tools)
│   ├── mcp-server-googlemaps/#    Google Maps (11 tools)
│   └── mcp-server-windsurf/  #    Windsurf IDE bridge (5 tools)
├── config/                   # ⚙️ Configuration Templates
├── scripts/                  # 🛠 DevOps & Diagnostic Utilities
├── tests/                    # 🧪 Test Suite (50+ tests)
├── docs/                     # 📚 Documentation (40+ files)
└── .github/                  # 🔄 CI/CD Workflows + Dependabot
```

---

## 🧪 Корисні Команди

```bash
# === Розробка ===
npm run dev                   # Запуск всього (Brain + UI + Electron + Proxy + Watcher)
npm run dev:brain             # Тільки Python Brain
npm run dev:renderer          # Тільки Vite UI
npm run dev:electron          # Тільки Electron

# === MCP ===
npm run mcp:status            # Стан всіх серверів
npm run mcp:status:json       # JSON формат
npm run mcp:validate          # Валідація конфігурацій
npm run test:sandbox          # Sandbox тестування MCP серверів

# === Діагностика ===
npm run verify                # Перевірка середовища
npm run redis:check           # Стан Redis
npm run redis:stop            # Зупинка Redis

# === Обслуговування ===
npm run clean                 # Очищення кешів
npm run clean:full            # Повне очищення пам'яті
npm run clean:golden          # Очищення Golden Fund
npm run clean:everything      # Очищення всього
npm run backup:golden         # Backup Golden Fund
npm run backup:all            # Backup всього

# === Діаграми ===
npm run diagram:auto-update   # Оновлення архітектурних діаграм
npm run diagram:export        # Експорт у PNG
npm run diagram:preview       # Перегляд
```

---

## 📜 Ліцензія

MIT

---

**AtlasTrinity** 🔱 _Recursive Intelligence for macOS_
