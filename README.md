# Discord Private Voice Bot

Полноценный Discord-бот для приватных временных голосовых комнат по механике Join to Create.

## Возможности

- Автоматическое создание временной комнаты при входе в `➕ Создать приват`.
- Автоматическое удаление комнаты, когда из неё вышел последний участник.
- Восстановление активных комнат из SQLite после перезапуска.
- Persistent панель управления в `🔊・voice-control`.
- Slash-команды `/voice ...` и `/voice-admin ...`.
- Пользовательские предпочтения: последнее имя комнаты, лимит, privacy mode, bitrate, allow/block списки.
- Защита от управления чужими комнатами и обычными серверными voice-каналами.
- Cooldown на кнопки и отдельный cooldown на переименование через панель.
- Проверки Discord permissions и обработка `Forbidden` / `HTTPException`.

## Структура

```text
discord-private-voice-bot/
├── bot.py
├── config.py
├── requirements.txt
├── .env.example
├── README.md
├── cogs/
│   ├── voice_events.py
│   ├── voice_commands.py
│   └── admin_commands.py
├── views/
│   ├── voice_panel.py
│   ├── modals.py
│   └── selects.py
├── database/
│   ├── database.py
│   └── models.py
└── utils/
    ├── permissions.py
    ├── logging.py
    └── helpers.py
```

## Создание Discord Application

1. Откройте [Discord Developer Portal](https://discord.com/developers/applications).
2. Нажмите **New Application**.
3. Введите название приложения и создайте его.
4. Откройте вкладку **Bot**.
5. Нажмите **Add Bot**.
6. Нажмите **Reset Token** или **Copy Token** и сохраните токен только в `.env`.

Никогда не вставляйте токен в исходный код и не публикуйте `.env`.

## Gateway Intents

В Developer Portal откройте **Bot** и включите:

- **Server Members Intent**: нужен для выбора участников, проверки владельца и восстановления пользовательских разрешений.
- **Voice States Intent**: нужен для отслеживания входа в `➕ Создать приват`, выхода из комнат и удаления пустых комнат.

`Message Content Intent` не нужен.

## Discord Permissions

Боту нужны следующие права:

- **Manage Channels**: создавать категорию, voice/text-каналы, менять overwrites, лимит участников, bitrate, удалять временные комнаты.
- **View Channels**: видеть созданные каналы и панель управления.
- **Send Messages**: отправлять панель управления и ответы setup-команд.
- **Embed Links**: отправлять красивую embed-панель и `/voice info`.
- **Connect**: корректно работать с голосовыми каналами и проверками доступа.
- **Speak**: иметь полноценный голосовой доступ в Create Room и временных комнатах.
- **Move Members**: переносить пользователя из `➕ Создать приват`, отключать rejected/kicked пользователей.
- **Mute Members**: выполнять `Mute` / `Unmute`.
- **Deafen Members**: выполнять `Deafen` / `Undeafen`.

Также при приглашении нужен scope **applications.commands**, чтобы slash-команды появились на сервере.

Позиция роли бота должна быть выше ролей пользователей, которыми он управляет.

## Роль Verified

`/voice-admin setup` ищет роль с названием `Verified`.

Если роль найдена, бот настраивает `Private Voice` и `➕ Создать приват` так:

- `@everyone`: `View Channel = False`, `Connect = False`;
- `Verified`: `View Channel = True`, `Connect = True`, `Speak = True`;
- бот: права на просмотр, подключение, управление каналами и перемещение участников.

Если роли `Verified` нет, бот использует `@everyone` как публичную роль и пишет предупреждение в ответе setup-команды.

В приватных комнатах роль `Verified` получает матрицу прав по состояниям:

- **Open + Visible**: `View Channel = True`, `Connect = True`, `Speak = True`.
- **Closed + Visible**: `View Channel = True`, `Connect = False`, `Speak = True`.
- **Open + Hidden**: `View Channel = False`, `Connect = True`, `Speak = True`.
- **Closed + Hidden**: `View Channel = False`, `Connect = False`, `Speak = True`.

`Close/Lock` управляет только `Connect`. `Hide/Show` управляет только `View Channel`. `Speak` не используется для ограничения входа.

Владелец и Allow List всегда получают `View Channel = True`, `Connect = True`, `Speak = True`. Block List получает персональный `Connect = False`.

## Invite URL

1. В Developer Portal откройте приложение.
2. Скопируйте **Application ID**.
3. Замените `CLIENT_ID` в ссылке:

```text
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=32525328&integration_type=0&scope=bot+applications.commands
```

Можно также собрать ссылку через **OAuth2 → URL Generator**:

- Scopes: `bot`, `applications.commands`
- Bot Permissions: права из раздела выше

## Установка

Требуется Python 3.12 или новее.

```bash
cd discord-private-voice-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Если команда `python3.12` недоступна, используйте установленный Python 3.12+:

```bash
python3 --version
python3 -m venv .venv
```

## Настройка .env

Скопируйте пример:

```bash
cp .env.example .env
```

Заполните:

```env
DISCORD_TOKEN=ваш_токен_бота
DATABASE_PATH=private_voice.sqlite3
LOG_LEVEL=INFO
SYNC_COMMANDS=true
```

`SYNC_COMMANDS=true` синхронизирует slash-команды при запуске. Глобальная синхронизация Discord иногда обновляется не мгновенно.

## Запуск

```bash
source .venv/bin/activate
python bot.py
```

После успешного запуска в консоли появится лог входа бота и синхронизации команд.

## Первоначальный setup

На сервере выполните:

```text
/voice-admin setup
```

Команда создаст:

- категорию `Private Voice`;
- голосовой канал `➕ Создать приват`;
- текстовый канал `🔊・voice-control`;
- persistent панель управления.

После этого пользователь заходит в `➕ Создать приват`, бот создаёт `Комната • username`, переносит пользователя и назначает владельцем.

## Команды пользователя

- `/voice lock` — закрыть комнату.
- `/voice unlock` — открыть комнату.
- `/voice hide` — скрыть комнату.
- `/voice show` — показать комнату.
- `/voice rename name:<название>` — переименовать комнату.
- `/voice limit limit:<0-99>` — установить лимит участников.
- `/voice permit member:<участник>` — разрешить вход пользователю.
- `/voice reject member:<участник>` — запретить вход пользователю и отключить его, если он внутри.
- `/voice kick member:<участник>` — отключить участника от комнаты без server ban.
- `/voice transfer member:<участник>` — передать владельца участнику комнаты.
- `/voice claim` — забрать комнату, если текущего владельца нет внутри.
- `/voice bitrate kbps:<число>` — изменить bitrate с учётом лимита сервера.
- `/voice delete` — удалить комнату после подтверждения.
- `/voice info` — показать название, владельца, участников, лимит, lock/visibility, bitrate и время создания.

## Админ-команды

- `/voice-admin setup` — создать инфраструктуру и панель.
- `/voice-admin reset` — удалить настройки, setup-каналы и временные комнаты бота.
- `/voice-admin config` — показать текущую конфигурацию.
- `/voice-admin cleanup` — удалить пустые временные комнаты и битые записи SQLite.

Админ-команды доступны только участникам с **Manage Server** или **Administrator**.

## Как работает восстановление после рестарта

Все активные временные комнаты записываются в таблицу `voice_channels`.

При запуске бот:

- регистрирует `VoicePanelView` как persistent view;
- загружает slash-команды;
- проверяет сохранённые комнаты;
- удаляет пустые временные комнаты;
- удаляет записи, если Discord-канал уже исчез;
- оставляет непустые комнаты активными, чтобы владелец и Claim продолжили работать.

## SQLite таблицы

Используются parameterized SQL queries через `aiosqlite`.

- `guild_settings`: настройки сервера и ID панели.
- `voice_channels`: активные временные комнаты.
- `voice_permissions`: allow/block для конкретной активной комнаты.
- `user_preferences`: предпочтения владельца.
- `user_preference_permissions`: сохранённые allow/block списки для новых комнат владельца.

## Поведение панели

Панель в `🔊・voice-control` постоянная. Кнопки используют стабильные `custom_id`, поэтому продолжают работать после перезапуска, если сообщение панели не удалено.

Ответы кнопок, select menu и modal отправляются ephemeral, чтобы действия владельца не засоряли канал.

## Безопасность

Бот проверяет, что:

- пользователь находится в управляемой временной комнате;
- комнатой управляет только текущий владелец;
- Claim доступен только когда владельца нет внутри;
- нельзя передать комнату боту;
- нельзя добавить бота в blacklist;
- нельзя запретить вход владельцу;
- нельзя выгнать владельца через его собственную панель;
- обычные серверные voice-каналы не затрагиваются;
- все изменения выполняются только для комнат из `voice_channels`;
- перед Discord-действиями проверяются права бота;
- ошибки Discord логируются и показываются пользователю аккуратным сообщением.

## Проверка

Базовая локальная проверка:

```bash
python -m compileall .
python -m unittest discover -s tests
python -c "import discord, aiosqlite, dotenv; print(discord.__version__)"
python -c "from views.voice_panel import VoicePanelView; v=VoicePanelView(); print(v.is_persistent(), len(v.children))"
```

Проверка в Discord после `/voice-admin setup`:

1. Зайти в `➕ Создать приват`.
2. Убедиться, что создана новая комната и пользователь перенесён.
3. Проверить `lock` / `unlock` через подключение другого пользователя.
4. Проверить `hide` / `show` с обычной роли.
5. Проверить `permit` / `reject`.
6. Проверить `transfer` / `claim`.
7. Проверить лимит участников.
8. Проверить bitrate выше и ниже лимита сервера.
9. Перезапустить бота и выполнить `/voice info` в активной комнате.
10. Проверить одновременный вход нескольких пользователей в `➕ Создать приват`.
