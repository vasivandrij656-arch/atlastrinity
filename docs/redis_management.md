# Redis Management for AtlasTrinity

AtlasTrinity використовує Redis для кешування, стану системи та повідомлень між сервісами.

## Проблема Race Condition

Раніше існувала проблема, коли AtlasTrinity стартував одночасно з Redis, що викликало помилки:
```
[STATE] Failed to publish event: Error 61 connecting to localhost:6379. Connection refused.
```

Це відбувалось тому, що Redis відповідав на `ping`, але ще не був готовий приймати з'єднання.

## ✅ **Вирішено**

Скрипти тепер очікують повної готовності Redis перед продовженням.

## Скрипти для керування Redis

### Перевірка та запуск Redis
```bash
npm run redis:check
```
- Перевіряє чи запущений Redis
- **Чекає на повну готовність** (до 30 секунд)
- Виконує тестову операцію (set/get) для перевірки
- Автоматично запускає якщо не працює
- Підтримує `brew services` та прямий запуск

### Зупинка Redis
```bash
npm run redis:stop
```
- Зупиняє Redis якщо запущений
- Працює з `brew services` та прямими процесами

### Автоматична перевірка в dev
Команда `npm run dev` тепер автоматично перевіряє Redis перед запуском:
```bash
npm run dev  # Автоматично включить redis:check + 2с затримка
```

## Як працює перевірка готовності:

1. **Basic ping:** Перевіряє базову відповідь Redis
2. **Test operation:** Виконує `set`/`get` операцію для тестування
3. **Wait loop:** Очікує до 30 секунд з прогрес-індикатором
4. **Stabilization:** Додаткова 2-секундна затримка в `dev` команді

## Встановлення Redis

### macOS (рекомендовано)
```bash
brew install redis
brew services start redis
```

### Перевірка вручну
```bash
redis-cli ping
# Повинно повернути PONG
```

## Усунення несправностей

### Помилка "Connection refused"
```bash
# Запустити Redis з повною перевіркою
npm run redis:check

# Або вручну
brew services start redis
```

### Redis не встановлено
```bash
brew install redis
```

### Перевірка статусу
```bash
brew services list | grep redis
# Або
ps aux | grep redis
```

### Якщо Redis запущений але помилки продовжуються
```bash
# Перезапустіть Redis
npm run redis:stop && npm run redis:check
```

## Конфігурація

Redis використовується за замовчуванням на `localhost:6379/0`. 
Можна змінити через змінну середовища `REDIS_URL`:

```bash
export REDIS_URL="redis://localhost:6379/0"
```

## Інтеграція з AtlasTrinity

- **StateManager:** Використовує Redis для публікації подій
- **Кешування:** Зберігання проміжних результатів
- **Координація:** Синхронізація між процесами

## Моніторинг

Після запуску `npm run dev` ви повинні бачити:
```
🔍 Checking Redis status...
✅ Redis is responding
⏳ Waiting for Redis to be fully ready...
✅ Redis is fully ready
⏳ Giving Redis 2 seconds to stabilize...
```

Якщо ви бачите це, помилки `Connection refused` не повинні повторюватись.
