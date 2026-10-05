# Первый проход

Нужен Python 3.10 или новее. Нет сторонних зависимостей, Docker, ключа модели или обязательного сервера.
Откройте репозиторий в Codex, Claude Code или Antigravity: модель этой среды пишет текст, Python — нет.

```bash
python mad.py init
python mad.py doctor
python mad.py knowledge-check
python mad.py search-plan
python mad.py topics
python mad.py new bridge-ports --problem com-pair
```

Затем поручите агенту:

> Используй mad-content для bridge-ports. Найди и прочитай источники проблемы. Проверь решение по
> документации MAD-auto. Уточни область применимости, не заполняй неизвестные версии. Делегируй
> инженерную, редакционную и поисковую проверки доступным отдельным агентам. Создай проверяемый пакет
> и предпросмотр, но не утверждай от имени человека и не публикуй.

`new` намеренно создаёт незаполненное задание. Источник добавляется из уже прочитанной разрешённой
выдержки или собственной фактологической заметки:

```bash
python mad.py source-add bridge-ports --id bridge-doc --kind official \
  --url https://mad-auto.ru/doc_wifi_adapters/svjaz_pk_s_ebu_po_wifi/index.html \
  --title 'Связь ПК с ЭБУ по WiFi' --locator 'Настройка COM-моста' --file reviewed-note.txt
python mad.py validate bridge-ports
python mad.py export bridge-ports
```

Проверяющий заполняет references в brief, sources/claims и разделы pack по образцу
`examples/article-demo/`. Пример — редакционный черновик по документации, не испытание и не разрешение
на публикацию. Отсутствующие данные не заменяются текстом из примера.

Для другой папки: `python mad.py install --target ../mad-editorial --dry-run`, затем та же команда
без dry-run. Установка проверяет конфликты заранее и отказывается перезаписывать пользовательский файл.
Повторный запуск обновляет только ранее управляемые неизменённые файлы. В отдельной папке выполните init.
Windows: используйте `py -3` вместо `python`, если команда python не настроена.
