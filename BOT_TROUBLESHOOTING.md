# 🔧 Диагностика и решение проблем с ботом

## 🚨 Бот упал - что делать?

### Шаг 1: Проверка статуса сервиса на сервере

Подключитесь к серверу через SSH и выполните:

```bash
sudo systemctl status travel-bot-api
```

**Что смотреть:**
- ✅ `Active: active (running)` - сервис работает
- ❌ `Active: failed` - сервис упал
- ⚠️ `Active: inactive (dead)` - сервис остановлен

### Шаг 2: Просмотр логов

**Последние 50 строк логов:**
```bash
sudo journalctl -u travel-bot-api -n 50
```

**Логи в реальном времени (для отслеживания):**
```bash
sudo journalctl -u travel-bot-api -f
```

**Логи за последний час:**
```bash
sudo journalctl -u travel-bot-api --since "1 hour ago"
```

**Поиск ошибок:**
```bash
sudo journalctl -u travel-bot-api | grep -i error
sudo journalctl -u travel-bot-api | grep -i exception
```

### Шаг 3: Перезапуск сервиса

**Если сервис упал:**
```bash
sudo systemctl restart travel-bot-api
```

**Проверка после перезапуска:**
```bash
sudo systemctl status travel-bot-api
```

**Если сервис не запускается:**
```bash
# Посмотрите детальные логи
sudo journalctl -u travel-bot-api -n 100 --no-pager

# Проверьте, что файлы на месте
ls -la /root/smm-travel-bot/api_server.py
ls -la /root/smm-travel-bot/bot.py

# Проверьте права доступа
ls -la /root/smm-travel-bot/
```

---

## 🔍 Типичные причины падения бота

### 1. Проблемы с подключением к Telegram API

**Симптомы в логах:**
```
TimeoutError
aiohttp.ClientConnectorError
TelegramAPIError
```

**Решение:**
- Проверьте интернет-соединение на сервере: `ping 8.8.8.8`
- Проверьте токен бота в `.env` файле
- Убедитесь, что бот не заблокирован в Telegram

### 2. Проблемы с базой данных

**Симптомы в логах:**
```
sqlite3.OperationalError
DatabaseError
```

**Решение:**
```bash
# Проверьте файл базы данных
ls -la /root/smm-travel-bot/travel_bot.db

# Проверьте права доступа
chmod 664 /root/smm-travel-bot/travel_bot.db
chown root:root /root/smm-travel-bot/travel_bot.db
```

### 3. Проблемы с OpenAI API

**Симптомы в логах:**
```
OpenAIError
APIError
AuthenticationError
```

**Решение:**
- Проверьте API ключ OpenAI в `.env` файле
- Убедитесь, что на счету OpenAI есть средства
- Проверьте лимиты API

### 4. Проблемы с виртуальным окружением

**Симптомы в логах:**
```
ModuleNotFoundError
ImportError
```

**Решение:**
```bash
# Активируйте виртуальное окружение
cd /root/smm-travel-bot
source venv/bin/activate

# Проверьте установленные пакеты
pip list

# Переустановите зависимости
pip install -r requirements.txt
```

### 5. Проблемы с файлами

**Симптомы в логах:**
```
FileNotFoundError
PermissionError
```

**Решение:**
```bash
# Проверьте права доступа
cd /root/smm-travel-bot
ls -la

# Установите правильные права
chmod 644 *.py
chmod 755 /root/smm-travel-bot
```

### 6. Проблемы с памятью

**Симптомы:**
- Сервис перезапускается постоянно
- Сервер зависает

**Решение:**
```bash
# Проверьте использование памяти
free -h

# Проверьте использование диска
df -h

# Посмотрите процессы Python
ps aux | grep python
```

---

## 🔄 Автоматический перезапуск

Бот должен автоматически перезапускаться при ошибках. Это настроено в двух местах:

### 1. В коде (`api_server.py`)

Функция `run_bot()` имеет цикл перезапуска:
```python
while True:
    try:
        await bot_main()
    except Exception as e:
        logger.error(f"❌ Ошибка в работе бота: {e}")
        await asyncio.sleep(10)  # Перезапуск через 10 секунд
```

### 2. В systemd сервисе (`travel-bot-api.service`)

```ini
Restart=always
RestartSec=10
```

**Проверка настроек systemd:**
```bash
cat /etc/systemd/system/travel-bot-api.service
```

**Перезагрузка конфигурации systemd:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart travel-bot-api
```

---

## 🛠️ Полная переустановка сервиса (если ничего не помогает)

```bash
# 1. Остановите сервис
sudo systemctl stop travel-bot-api

# 2. Удалите старый сервис
sudo systemctl disable travel-bot-api
sudo rm /etc/systemd/system/travel-bot-api.service

# 3. Пересоздайте сервис
sudo nano /etc/systemd/system/travel-bot-api.service
```

Вставьте содержимое:
```ini
[Unit]
Description=SMM Travel Bot API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/smm-travel-bot
Environment="PATH=/root/smm-travel-bot/venv/bin"
ExecStart=/root/smm-travel-bot/venv/bin/python /root/smm-travel-bot/api_server.py
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=travel-bot-api

[Install]
WantedBy=multi-user.target
```

```bash
# 4. Перезагрузите systemd
sudo systemctl daemon-reload

# 5. Запустите сервис
sudo systemctl enable travel-bot-api
sudo systemctl start travel-bot-api

# 6. Проверьте статус
sudo systemctl status travel-bot-api
```

---

## 📊 Мониторинг бота

### Настройка мониторинга статуса:

**Проверка каждые 5 минут (cron):**
```bash
crontab -e
```

Добавьте:
```
*/5 * * * * systemctl is-active --quiet travel-bot-api || systemctl restart travel-bot-api
```

### Скрипт для проверки:

Создайте файл `/root/check_bot.sh`:
```bash
#!/bin/bash
if ! systemctl is-active --quiet travel-bot-api; then
    echo "Bot is down! Restarting..."
    systemctl restart travel-bot-api
    # Отправить уведомление (если нужно)
    # curl -X POST https://api.telegram.org/bot<TOKEN>/sendMessage -d "chat_id=<CHAT_ID>&text=Bot перезапущен"
fi
```

Сделайте исполняемым:
```bash
chmod +x /root/check_bot.sh
```

---

## 📝 Чеклист диагностики

- [ ] Проверить статус сервиса: `sudo systemctl status travel-bot-api`
- [ ] Проверить логи: `sudo journalctl -u travel-bot-api -n 50`
- [ ] Проверить интернет: `ping 8.8.8.8`
- [ ] Проверить файлы на месте: `ls -la /root/smm-travel-bot/*.py`
- [ ] Проверить права доступа: `ls -la /root/smm-travel-bot/`
- [ ] Проверить виртуальное окружение: `source venv/bin/activate && pip list`
- [ ] Проверить переменные окружения: `cat /root/smm-travel-bot/.env`
- [ ] Проверить использование ресурсов: `free -h && df -h`
- [ ] Перезапустить сервис: `sudo systemctl restart travel-bot-api`

---

## 🔗 Полезные команды

**Перезапуск сервиса:**
```bash
sudo systemctl restart travel-bot-api
```

**Остановка сервиса:**
```bash
sudo systemctl stop travel-bot-api
```

**Запуск сервиса:**
```bash
sudo systemctl start travel-bot-api
```

**Просмотр логов в реальном времени:**
```bash
sudo journalctl -u travel-bot-api -f
```

**Просмотр последних 100 строк:**
```bash
sudo journalctl -u travel-bot-api -n 100
```

**Очистка старых логов:**
```bash
sudo journalctl --vacuum-time=7d
```

---

## 📞 Если проблема не решается

1. Сохраните логи:
   ```bash
   sudo journalctl -u travel-bot-api > /tmp/bot_logs.txt
   ```

2. Проверьте версию Python:
   ```bash
   /root/smm-travel-bot/venv/bin/python --version
   ```

3. Попробуйте запустить вручную для отладки:
   ```bash
   cd /root/smm-travel-bot
   source venv/bin/activate
   python api_server.py
   ```

