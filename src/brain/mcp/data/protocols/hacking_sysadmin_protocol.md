# Hacking & Sysadmin Protocol (v1.0)

=====================================

## 🎯 ПРИЗНАЧЕННЯ

Цей протокол призначений для автономної роботи в мережевих середовищах, виконання завдань з адміністрування та тестування на проникнення.

## 🚨 ОСНОВНІ ПРАВИЛА (MANDATORY)

1. **АНАЛІЗ СЕРЕДОВИЩА ПЕРЕД ДІЄЮ (IFCONFIG FIRST)**:
   - ЗАБОРОНЕНО починати сканування мережі (`nmap`), не знаючи власної IP-адреси та маски підмережі.
   - ПЕРШИМ КРОКОМ при роботі з мережею завжди має бути: `ifconfig`, `ip addr` або `netstat -rn`.
   - Визнач активний інтерфейс (той, що має IP) і використовуй його підмережу для подальшого пошуку.

2. **ПРЕЦИЗІЙНЕ СКАНУВАННЯ (PRECISION SCANNING)**:
   - Не використовуй дефолтні діапазони (`192.168.1.0/24`), якщо ти не впевнена, що ціль там.
   - Використовуй `-sV` для визначення версій сервісів.
   - Завжди перевіряй альтернативні порти для SSH (22, 2222, 22222) та HTTP (80, 8080, 8443).

3. **MIKROTIK & KALI INTERACTION**:
   - При роботі з MikroTik використовуй SSH-ключі. Якщо ключ не вказано, шукай його в `~/.ssh/` або в конфігах проекту.
   - Якщо MikroTik використовується для моніторингу, пам'ятай про TZSP-стрімінг пакетів на IP-адресу Kali Linux для аналізу через Wireshark/Tcpdump.
   - Перевіряй модель MikroTik (`/system resource print`) для розуміння апаратних обмежень (Wi-Fi sniffing, pcap export).
   - **REFERENCE**: See `mikrotik_network_protocol.md` for complete connection details and logging configuration.

4. **KALI LINUX & VIRTUALBOX**:
   - Враховуй, що Kali у VirtualBox зазвичай працює через NAT або Bridged адаптер. Це обмежує прямий доступ до Wi-Fi заліза хоста.
   - Весь мережевий взлом (Wi-Fi scanning/deauth) має виконуватися на MikroTik, а Kali — як аналітичний центр.

5. **TROUBLESHOOTING DOCTRINE**:
   - Якщо `nmap` повернув EMPTY output — перевір, чи ти не в ізольованій підмережі.
   - Якщо SSH відхилено (Connection refused) — спробуй просканувати інші порти цього хоста.
   - Якщо файл не передається — перевір правила Firewall (`/ip firewall filter print` на MikroTik).

## 🛠 ТЕХНІЧНИЙ СТЕК

- **Discovery**: `nmap`, `arp -a`, `ping -c 3`
- **Analysis**: `tcpdump`, `wireshark` (через Vision), `aircrack-ng` (на Kali)
- **Control**: `ssh`, `scp`, `VBoxManage`
- **MikroTik**: RouterOS CLI commands
