# Telegram Clock Avatar

Скрипт для личного аккаунта Telegram: раз в минуту генерирует аватарку с текущим временем и загружает ее как фото профиля.

## Важно

- Для личного аккаунта нужен не bot token, а `API_ID` и `API_HASH` с https://my.telegram.org.
- Код входа из Telegram и пароль 2FA вводи только в консоли при первом запуске. Не отправляй их в чат.
- Обновление каждую секунду не подходит: Telegram кэширует аватарки и может выдать FloodWait. Реалистичный режим - раз в минуту.

## Установка

Открой PowerShell:

```powershell
cd $HOME\telegram-clock-avatar
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

В `.env` вставь:

```env
API_ID=...
API_HASH=...
PHONE=+998...
```

## Проверка картинки

```powershell
.\run.ps1 -Preview
```

Файл появится как `clock-avatar.jpg`.

## Одно обновление аватарки

```powershell
.\run.ps1 -Once
```

При первом запуске Telegram пришлет код входа. Введи его в консоли. Если включен облачный пароль, Telethon попросит и его.

## Постоянный запуск

```powershell
.\run.ps1
```

Окно PowerShell должно оставаться открытым. Позже можно добавить запуск через Windows Task Scheduler.

Если увидишь ошибку про `TIMEZONE`, установи зависимости из `requirements.txt` или оставь в `.env` строку `UTC_OFFSET=+05:00` для Ташкента.

## Render

Для Render не загружай файл `telegram_clock_avatar.session` в GitHub. Вместо этого создай строку сессии локально:

```powershell
cd $HOME\telegram-clock-avatar
.\run.ps1 -SessionString
```

Скопируй строку после `TELETHON_SESSION_STRING=` и добавь ее в Render в Environment Variables.

Рекомендуемый тип сервиса: Background Worker.

Настройки Render:

```text
Build Command: pip install -r requirements.txt
Start Command: python clock_avatar.py
```

Environment Variables:

```env
API_ID=...
API_HASH=...
TELETHON_SESSION_STRING=...
TIMEZONE=Asia/Tashkent
UTC_OFFSET=+05:00
UPDATE_SECONDS=60
DELETE_PREVIOUS_SCRIPT_PHOTOS=true
SHOW_DATE=true
DATE_FORMAT=%d.%m.%Y
```

`PHONE` на Render не нужен, если есть `TELETHON_SESSION_STRING`.
