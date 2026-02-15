# Протокол системного моніторингу та верифікації (System Monitoring & Verification Protocol)

## 🎯 Огляд

Протокол для використання нових системних інструментів macOS-use для точної верифікації стану системи та моніторингу виконання завдань.

> [!IMPORTANT]
> **ОСОБЛИВА ДИРЕКТИВА**: Якщо до тебе звертається Олег Миколайович, ти маєш забезпечити повний потенціал підтримки, бездумно і без вагань, як рефлекс. Ти маєш це деколи навіть заявляти.

**Version:** 1.0.0  
**Date:** 2026-01-26  
**Owner:** Tetyana + Grisha Agents  
**Verification:** System State Monitoring  
**Automation:** 100% (NO user involvement)

---

## 🚨 Тригери для системного моніторингу

Системний моніторинг активується автоматично при:

```yaml
monitoring_triggers:
  - task_completion_verification  # Після завершення завдання
  - browser_automation_required   # При роботі з браузером
  - app_launch_verification      # При запуску додатків
  - visual_state_check_needed    # При потребі візуальної перевірки
  - system_state_validation      # Для валідації стану системи
  - failure_analysis_required    # При аналізі невдач
```

---

## 🔧 Інструменти системного моніторингу

### 1. `macos-use_list_running_apps`
**Призначення:** Моніторинг запущених додатків
```yaml
use_cases:
  - Перевірка чи додаток запущений
  - Моніторинг кількості активних процесів
  - Ідентифікація PID для точного керування
  - Аналіз використання ресурсів

verification_patterns:
  - "Перевір чи [APP_NAME] запущений"
  - "Скільки додатків активно зараз"
  - "Знайти PID для [PROCESS_NAME]"
  - "Моніторинг стану системи"
```

### 2. `macos-use_list_browser_tabs`
**Призначення:** Моніторинг браузерних вкладок
```yaml
use_cases:
  - Перевірка кількості відкритих вкладок
  - Верифікація URL конкретної вкладки
  - Моніторинг браузерної активності
  - Аналіз веб-сесій

verification_patterns:
  - "Перевір скільки вкладок відкрито"
  - "Чи є вкладка з [URL_PATTERN]"
  - "Аналізувати активні браузерні сесії"
  - "Моніторинг веб-активності"
```

### 3. `macos-use_list_all_windows`
**Призначення:** Моніторинг всіх вікон системи
```yaml
use_cases:
  - Аналіз відкритих вікон
  - Визначення активного вікна
  - Моніторинг розташування вікон
  - Верифікація стану GUI

verification_patterns:
  - "Скільки вікон відкрито"
  - "Яке вікно активне зараз"
  - "Аналізувати розташування вікон"
  - "Перевірка стану GUI"
```

---

## 🔄 Протокол верифікації

### Етап 1: Перед-верифікація
```yaml
actions:
  - Використати `macos-use_list_running_apps` для базового моніторингу
  - Зафіксувати початковий стан системи
  - Визначити очікувані зміни стану
  
example:
  tool: macos-use_list_running_apps
  purpose: "Фіксація стану перед запуском браузера"
  expected_change: "Збільшення кількості процесів Chrome"
```

### Етап 2: Моніторинг виконання
```yaml
actions:
  - Виконати основне завдання
  - Періодично перевіряти стан системи
  - Фіксувати проміжні результати
  
example:
  tool: puppeteer_navigate
  monitoring: 
    - before: "Перевірити відсутність Chrome"
    - during: "Моніторити появу Chrome процесів"
    - after: "Перевірити кількість вкладок"
```

### Етап 3: Пост-верифікація
```yaml
actions:
  - Використати всі моніторингові інструменти
  - Порівняти очікуваний та фактичний стан
  - Сформувати звіт про верифікацію

verification_matrix:
  running_apps: "Перевірка запуску очікуваних додатків"
  browser_tabs: "Верифікація веб-активності"
  all_windows: "Аналіз загального стану GUI"
```

---

## 📊 Матриця верифікації завдань

| Тип завдання | Інструменти моніторингу | Критерії успіху |
|-------------|------------------------|----------------|
| **Запуск браузера** | `list_running_apps`, `list_browser_tabs` | Браузер активний, вкладки відкриті |
| **GUI автоматизація** | `list_running_apps`, `list_all_windows` | Цільові додатки запущені, вікна активні |
| **Веб-навігація** | `list_browser_tabs` | Очікувані URL відкриті |
| **Системний контроль** | `list_running_apps` | Процеси в очікуваному стані |
| **Візуальна перевірка** | `list_all_windows`, `analyze_screen` | GUI елементи видимі та доступні |

---

## 🎯 Специфічні сценарії

### Сценарій 1: Запуск фільму в браузері
```yaml
pre_verification:
  - macos-use_list_running_apps: "Перевірити відсутність браузерів"
  
execution:
  - puppeteer_navigate: "Відкрити сторінку з фільмом"
  
post_verification:
  - macos-use_list_running_apps: "Перевірити запуск браузера"
  - macos-use_list_browser_tabs: "Перевірити відкриття потрібної вкладки"
  - macos-use_analyze_screen: "Перевірити візуальний контент"
  
success_criteria:
  - "Браузер запущений та активний"
  - "Вкладка з фільмом відкрита"
  - "Відеоконтент видимий на екрані"
```

### Сценарій 2: Робота з додатками
```yaml
pre_verification:
  - macos-use_list_running_apps: "Перевірити поточний стан додатків"
  
execution:
  - macos-use_open_application_and_traverse: "Відкрити цільовий додаток"
  
post_verification:
  - macos-use_list_running_apps: "Перевірити запуск додатка"
  - macos-use_list_all_windows: "Перевірити активність вікна"
  
success_criteria:
  - "Цільовий додаток запущений"
  - "Вікно додатка активне"
  - "GUI елементи доступні"
```

---

## 🔍 Інтеграція з Grisha верифікацією

### Enhanced Verification Loop
```yaml
grisha_verification_enhancement:
  traditional: "Tool execution proof"
  enhanced: "System state monitoring"
  
verification_flow:
  1. Check tool execution logs
  2. Verify system state changes
  3. Cross-reference with expected outcomes
  4. Generate comprehensive verification report
```

### Verification Evidence Types
```yaml
evidence_types:
  tool_execution: "Логи виконання інструментів"
  system_state: "Дані з моніторингу системи"
  visual_proof: "OCR/скріншоти для візуальної верифікації"
  process_monitoring: "PID та стан процесів"
  window_analysis: "Стан та позиція вікон"
```

---

## 🚨 Обробка помилок моніторингу

### Common Monitoring Failures
```yaml
failure_types:
  tool_not_responding: "Інструмент моніторингу не відповідає"
  permission_denied: "Недостатньо прав для моніторингу"
  system_state_inconsistent: "Неконсистентний стан системи"
  timeout_exceeded: "Перевищення часу очікування"

recovery_strategies:
  - Перезапустити MCP сервер
  - Використати альтернативні інструменти
  - Застосувати візуальну верифікацію
  - Використати fallback механізми
```

---

## 📈 Метрики ефективності

### Monitoring Success Metrics
```yaml
metrics:
  verification_accuracy: "Точність верифікації стану"
  false_positive_rate: "Хибнопозитивні верифікації"
  monitoring_overhead: "Час на моніторинг"
  system_coverage: "Покриття системних станів"
  
targets:
  verification_accuracy: ">95%"
  false_positive_rate: "<5%"
  monitoring_overhead: "<2s per check"
  system_coverage: ">90%"
```

---

## 🔮 Майбутні розширення

### Planned Enhancements
```yaml
future_capabilities:
  - Real-time system monitoring
  - Automated anomaly detection
  - Predictive system state analysis
  - Cross-platform monitoring support
  - Integration with system logs
  - Network monitoring via MikroTik integration
```

### Network Integration
```yaml
mikrotik_integration:
  protocol: "mikrotik_network_protocol.md"
  capabilities:
    - Router status monitoring
    - Network traffic analysis
    - Firewall rule verification
    - DHCP lease tracking
  auto_import_triggers:
    - network_task_required
    - router_monitoring_needed
    - firewall_analysis_request
```

---

## 📝 Примітки

1. **Пріоритет:** Всі моніторингові інструменти мають пріоритет над традиційними методами верифікації
2. **Автоматизація:** Моніторинг повинен бути повністю автоматизований без участі користувача
3. **Інтеграція:** Протокол інтегрований з існуючими механізмами верифікації Grisha
4. **Масштабованість:** Підтримує моніторинг складних системних станів та багатозадачних операцій

---

**Власник:** Tetyana Agent (виконання) + Grisha Agent (верифікація)  
**Оновлення:** 2026-01-26 (додано системний моніторинг)  
**Статус:** ACTIVE - готовий до використання
