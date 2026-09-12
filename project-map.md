# Project map

Карта внешних корней для AI-агентов и docs. Не путать с каноном экосистемы
`my-study-bot-meta/docs/projects-map.md` (сервис → путь внутри meta).

| Key | Relative path (from this repo root) | Notes |
|-----|-------------------------------------|--------|
| my-study-bot-meta | ../my-study-bot-meta | Sibling layout: `my-study-bot` рядом с `my-study-bot-meta` |

## Resolution

1. Взять путь по ключу `my-study-bot-meta` относительно **корня этого репозитория** (каталог, где лежит этот файл).
2. Считать корень валидным, если существует `{my-study-bot-meta}/docs/projects-map.md`.
3. Если путь не существует / файл не найден — **спросить у пользователя** абсолютный путь к `my-study-bot-meta` и использовать его до конца сессии (не угадывать sibling `../my-study-bot-meta` молча).

## Docs links

В markdown этого репозитория ссылки на канон писать как:

- `my-study-bot-meta/docs/projects-map.md`
- `my-study-bot-meta/docs/...`

Агент резолвит префикс `my-study-bot-meta/` через ключ выше. Не использовать `../../docs/...`.
