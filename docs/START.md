# Первый проход

Нужен Python 3.10+. Зависимости устанавливать не требуется. Откройте репозиторий в своей среде ИИ:
модель и её реальные средства поиска собирают материалы, Python проверяет файлы и экспортирует.

```bash
python mad.py init
python mad.py doctor
python mad.py knowledge-check
python mad.py sources
python mad.py search-plan
python mad.py research-new market-first --days 30
```

Поручите агенту mad-research: найти реальные проблемы и попытки решения по
[каталогу сообществ](COMMUNITIES.md), проверить документацию MAD-auto и заполнить исследование.
[Поля отчёта и требования](RESEARCH-FIRST.md). Пустой research.json намеренно не проходит проверку.
Недоступные соцсети указываются явно, описание ролика не выдаётся за просмотр.

После поиска, чтения и анализа рынка:

```bash
python mad.py research-check market-first
python mad.py plan-build market-first
python mad.py new bridge-ports --problem com-pair --research market-first
```

Один отчёт может обосновывать несколько статей. Допускается переиспользовать исследование не старше
7 дней для подходящей темы. Архивный вопрос не считается новым трендом.
`new` берёт пользу и ограничения из плана, но не пишет статью. Затем агент заполняет brief,
sources/claims и pack, прикладывает настоящие снимки или проверенные схемы.

```bash
python mad.py source-add bridge-ports --id bridge-doc --kind official \
  --url https://mad-auto.ru/doc_wifi_adapters/svjaz_pk_s_ebu_po_wifi/index.html \
  --title 'Связь ПК с ЭБУ по WiFi' --locator 'Настройка COM-моста' --file reviewed-note.txt
python mad.py validate bridge-ports
python mad.py export bridge-ports
```

Источники добавляются из уже прочитанных разрешённых выдержек или собственных фактологических заметок.
Пример в examples/article-demo — архивный черновик, не испытание и не готовое исследование.
Для существующего задания выполните research-link после нового плана и повторите приёмку.

Установка отдельно: `python mad.py install --target ../mad-editorial --dry-run`, затем без dry-run.
В новой папке выполните init. Установщик отказывается перезаписывать изменённые пользовательские файлы.
Windows: при необходимости замените python на py -3. Ключи моделей CLI не нужны.
