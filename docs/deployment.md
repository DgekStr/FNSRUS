# Развёртывание на Ubuntu 24.04

Рабочий контейнер: `192.168.0.45`. Подключение: `ssh root@192.168.0.45`.
Команды подготовки выполняются от root, приложение — от `deploy:www-data`.

## 1. Система и пользователь

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
apt-get install -y python3-venv python3-dev build-essential curl ca-certificates nginx sudo git
id deploy || useradd --system --create-home --home-dir /home/deploy --shell /bin/bash --user-group deploy
usermod -aG sudo,www-data deploy
install -d -o deploy -g www-data -m 0750 /srv/mcp-fns
```

Пользователь входит в группу sudo; пароль и passwordless-sudo не создаются.
Для обслуживания в этой инструкции используется SSH root и `runuser`.

## 2. uv и MCP-пакет

```bash
cd /srv/mcp-fns
runuser -u deploy -- python3 -m venv /home/deploy/.local/uv
runuser -u deploy -- /home/deploy/.local/uv/bin/pip install uv
runuser -u deploy -- mkdir -p /home/deploy/.local/bin
runuser -u deploy -- ln -sf /home/deploy/.local/uv/bin/uv /home/deploy/.local/bin/uv
runuser -u deploy -- ln -sf /home/deploy/.local/uv/bin/uvx /home/deploy/.local/bin/uvx
runuser -u deploy -- /home/deploy/.local/bin/uv --version
runuser -u deploy -- /home/deploy/.local/bin/uvx --version
runuser -u deploy -- /home/deploy/.local/bin/uvx --from atomno-mcp-fns-check==0.1.12 atomno-mcp-fns-check --help
runuser -u deploy -- /home/deploy/.local/bin/uvx --from atomno-mcp-egrul==0.1.10 atomno-mcp-egrul --version
```

Запускайте uv из `/srv/mcp-fns`, не из `/root`: иначе uv пытается искать
конфигурацию в закрытом для deploy каталоге. Подпрограмма работает через
`uvx --offline` с закреплённой версией, поэтому предварительное скачивание обязательно.
Не удаляйте кэш uv без повторного скачивания пакета.

### Первичная загрузка данных ЕГРЮЛ

`mcp-egrul` не скачивает снимок автоматически. Сначала примите условия
распространения open-data на сайте ФНС, затем вручную получите официальные ZIP
файлы ЕГРЮЛ и поместите их в `/var/lib/mcp-fns/dumps/egrul/<дата>/`.
Полный набор занимает около 15 ГБ; первичный импорт по оценке upstream занимает
30-60 минут. Проверьте свободное место до загрузки.

```bash
install -d -o deploy -g www-data -m 0750 /var/lib/mcp-fns/dumps/egrul/2026-10-14
# Скопируйте официальные ZIP-выгрузки в созданный каталог после принятия условий ФНС.
runuser -u deploy -- env \
  MCP_EGRUL_DB=/var/lib/mcp-fns/egrul.sqlite \
  MCP_EGRUL_DUMPS_DIR=/var/lib/mcp-fns/dumps \
  /home/deploy/.local/bin/uvx --from atomno-mcp-egrul==0.1.10 \
  atomno-mcp-egrul-import --registry egrul --full
```

Первый импорт выполняется вручную, а не из HTTP-запроса. Пока база пуста,
поиск вернёт явное сообщение о необходимости импорта; он не будет сообщать,
что компания не найдена.

## 3. Файлы и зависимости

Из Windows, до инициализации локального Git, можно передать полный проект:

```powershell
scp -r C:/_project_/FNSRUS/. root@192.168.0.45:/srv/mcp-fns/
```

После появления `.git` передавайте только файлы проекта, исключая `.git`,
venv, `.env`, SQLite и резервные копии. Пример передачи рабочих каталогов:

```powershell
scp -r C:/_project_/FNSRUS/templates C:/_project_/FNSRUS/static C:/_project_/FNSRUS/systemd C:/_project_/FNSRUS/nginx C:/_project_/FNSRUS/docs root@192.168.0.45:/srv/mcp-fns/
scp C:/_project_/FNSRUS/server.py C:/_project_/FNSRUS/api_fns.py C:/_project_/FNSRUS/test_server.py C:/_project_/FNSRUS/VERSION C:/_project_/FNSRUS/requirements.txt C:/_project_/FNSRUS/README.md C:/_project_/FNSRUS/LICENSE C:/_project_/FNSRUS/.env.example root@192.168.0.45:/srv/mcp-fns/
```

На сервере:

```bash
cd /srv/mcp-fns
chown -R deploy:www-data templates static systemd nginx docs
chown deploy:www-data server.py api_fns.py test_server.py VERSION requirements.txt README.md LICENSE .env.example
find templates static systemd nginx docs -type d -exec chmod 0750 {} +
find templates static systemd nginx docs -type f -exec chmod 0640 {} +
runuser -u deploy -- /home/deploy/.local/bin/uv venv .venv --python /usr/bin/python3
runuser -u deploy -- /home/deploy/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
runuser -u deploy -- .venv/bin/python -m py_compile server.py api_fns.py
runuser -u deploy -- .venv/bin/python -m unittest test_server -v
```

Nginx работает от www-data и читает статику по правам группы.
Существующее venv не пересоздавайте без необходимости; для обновления достаточно
команды `uv pip install` с текущим requirements.txt.

## 4. systemd

```bash
cd /srv/mcp-fns
systemd-analyze verify systemd/mcp-fns-ui.service
install -m 0644 systemd/mcp-fns-ui.service /etc/systemd/system/mcp-fns-ui.service
systemctl daemon-reload
systemctl enable --now mcp-fns-ui
```

Если нужна отдельная конфигурация, скопируйте шаблон:

```bash
install -m 0600 .env.example /etc/mcp-fns.env
```

Отредактируйте его непосредственно на сервере и перезапустите сервис.
`FNS_API_KEY` можно задать как начальный ключ API-ФНС; предпочтительнее настройка
через UI, чтобы не менять окружение и не перезапускать сервис. В шаблоне ключ пустой.
Основные параметры: `HOST`, `PORT`, `LOG_LEVEL`, `UVX_PATH`,
`MCP_FNS_REGISTRIES_DB`, `FNS_SETTINGS_PATH`. Смена порта требует соответствующего изменения Nginx.
Сеть доступа к настройкам задаётся `FNS_SETTINGS_LAN_NETWORKS` (по умолчанию
`192.168.0.0/24,10.1.17.6/32,127.0.0.0/8,::1/128`). Изменяйте allowlist только на доверенные
подсети; внешний доступ к `/api/settings/*` отвечает 403.
В systemd для `mcp-egrul` закреплены `MCP_EGRUL_DB=/var/lib/mcp-fns/egrul.sqlite`
и `MCP_EGRUL_DUMPS_DIR=/var/lib/mcp-fns/dumps`.

Сохранённые через UI настройки находятся в `/var/lib/mcp-fns/api-fns-settings.json`
с владельцем deploy и правами 0600. Этот файл содержит секрет: не выводите его
в журнал, не включайте в Git, обычные архивы проекта или общедоступные резервные
копии. Явно сохранённые настройки имеют приоритет над ключом из окружения;
удаление ключа в UI отключает интеграцию и после перезапуска.

Юнит задаёт 512 МБ RAM, 80% CPU, перезапуск через 5 секунд при сбое,
чтение проекта без записи и отдельный `/var/lib/mcp-fns` для реестров.
`uvx --offline` всё равно пишет в `~/.local/share/uv/tools`, поэтому
разрешены записи и в этот каталог, и в `~/.cache/uv`.
SQLite карточек создаётся в PrivateTmp и удаляется после вызова.

## 5. Nginx

Перед изменением существующей установки сохраните текущий конфиг.
Если порт 80 занят другим сайтом, не отключайте его без согласования.

```bash
cd /srv/mcp-fns
install -m 0644 nginx/mcp-fns.conf /etc/nginx/sites-available/mcp-fns
ln -sfn /etc/nginx/sites-available/mcp-fns /etc/nginx/sites-enabled/mcp-fns
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx
```

Статика `/static/` читается напрямую. Остальные запросы проксируются на
`127.0.0.1:8000`, таймаут чтения 60 секунд, размер запроса до 1 МБ.

## 6. Проверка

```bash
systemctl is-active mcp-fns-ui nginx
systemctl is-enabled mcp-fns-ui nginx
systemctl show mcp-fns-ui -p MemoryMax -p CPUQuotaPerSecUSec -p MemoryCurrent
curl -fsS --retry 10 --retry-delay 1 --retry-all-errors --max-time 3 http://127.0.0.1/healthz
curl -fsS http://127.0.0.1/static/app.js -o /dev/null
curl -s http://127.0.0.1/api/check -H 'Content-Type: application/json' -d '{"identifier":"7707083893"}'
curl -s http://127.0.0.1/api/search -H 'Content-Type: application/json' -d '{"query":"сбер"}'
```

Статус `active` сам по себе не подтверждает готовность HTTP или источников.
Откройте `http://192.168.0.45/`, проверьте Enter, очистку, неверный формат,
несуществующий ИНН и копирование. Размеры для проверки: 375, 768, 1440 px.
Сопоставьте количество конечных полей JSON с количеством полей карточки.

## 7. Обновление и откат

До изменения рабочего приложения сохраните исходники и установленные конфиги
в закрытом каталоге резервных копий. Не включайте их в Git.
Сначала проверьте новую версию в staging; затем установите файлы, выполните
`nginx -t`, `systemd-analyze verify` и перезапустите приложение.
При откате восстановите исходники и конфиги из той же копии, затем выполните
`systemctl daemon-reload`, перезапуск приложения и reload Nginx.
Рабочие реестры и старый SQLite-кэш карточек не удаляются при обновлении;
новая обвязка не переиспользует старый кэш карточек.

## 8. Сбои и защита доступа

```bash
journalctl -u mcp-fns-ui -n 100 --no-pager
ss -tlnp
```

- 502: проверьте PATH uvx, права и журнал подпроцесса.
- 504: обязательный источник не успел ответить; повторите позже.
- 429: подождите минуту; дополнительные частые повторы ухудшают ситуацию.
- Реестр пуст: используйте штатный `atomno-mcp-fns-etl` и официальные выгрузки.
  Реальные загрузки реестров — отдельная операция, тестовые seed-файлы не подходят.
- Ошибки ЕФРСБ / ФССП / КАД не означают отсутствия банкротства, взысканий или дел.
- На HTTP нет стандартного Clipboard API: работает резервный `execCommand('copy')`.
  В старом или ограниченном браузере разрешите копирование либо используйте HTTPS.

Не публикуйте сервис наружу без HTTPS и авторизации. В текущей установке
FastAPI доступен только через loopback; Basic-auth можно включить в Nginx,
задав пароль непосредственно через htpasswd, не через сообщения или код.
Публичный NAT и проброс портов эта установка не настраивает.

## 9. Локальный Git

В `C:\_project_\FNSRUS` должен быть только исходный проект: без SQLite, venv,
паролей, токенов и журналов. `.gitignore` исключает эти файлы,
`.gitattributes` фиксирует LF для текста.

Исходники опубликованы в https://github.com/DgekStr/FNSRUS.
Для воспроизводимой установки используйте тег `1.0`, а не изменяемую ветку:

```bash
git clone --branch 1.0 --depth 1 https://github.com/DgekStr/FNSRUS.git FNSRUS
cd FNSRUS
cat VERSION
```

Git и GitHub Release содержат только исходники, документацию и скриншоты.
Рабочую базу и файл ключа переносите отдельно по защищённому каналу.
Публикация обновлений выполняется только по явному поручению владельца.
Авторство настраивается локально в репозитории, глобальные настройки не меняются.