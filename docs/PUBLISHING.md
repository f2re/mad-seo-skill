# Передача на новый сайт

Сайт `m.wifiobd.ru` уже отдаёт содержимое главной страницы в публичном HTML. Это не доказывает
индексируемость всех страниц, но исключает предположение, будто главная целиком пуста без JavaScript.
Наличие проверяемого API публикации в CMS не установлено. WordPress не предполагается.

```bash
python mad.py validate bridge-ports
python mad.py export bridge-ports
python mad.py review-template bridge-ports
python mad.py status bridge-ports
# Человек проверяет preview.html, заполняет review.json и поручает утверждение:
python mad.py approve bridge-ports --confirm 'bridge-ports@ПОЛНЫЙ_SHA256'
python mad.py export bridge-ports --approved
```

В `exports/<slug>/approved/`: article.html, article.md, preview.html, cms-payload.json,
structured-data.json, manifest.json и выбранные изображения. Это локальный пакет, не публикация.
Не загружайте preview.html как страницу сайта: в нём намеренно есть noindex.
Для CMS используются article.html и метаданные; медиа получают окончательные публичные URL,
которые заменяют относительные ссылки. Автор, даты, canonical и действие new/update/merge
проверяются перед импортом. Дата нового размещения задаётся самой CMS по факту, а не заранее агентом.

Не перезаписывать корневые robots.txt, sitemap, маршруты или существующую статью вслепую.
При смене домена требуется отдельная поадресная карта старый→новый и проверка перенаправлений.
Пока владелец не утвердил перенос, `wifiobd.ru` и `m.wifiobd.ru` рассматриваются раздельно.
Повторный экспорт не создаёт новых публикаций. Изменённый текст/источник/правило требует повторной приёмки.
