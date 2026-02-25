# Настройка Git и первый push в GitHub

Репозиторий: **https://github.com/SoapMaker101/gigabot**

Текущая папка — копия кода без `.git`. Чтобы загрузить изменения в GitHub, выполни команды **из папки `gigabot`** (корень проекта, где лежит `pyproject.toml`).

---

## Вариант 1: Инициализация в текущей папке и связь с GitHub

Открой PowerShell и выполни по порядку:

```powershell
cd "c:\Прочее\Крипта\nanobot-main\gigabot"

git init
git remote add origin https://github.com/SoapMaker101/gigabot.git
git fetch origin
git branch -M main
git reset --soft origin/main
git add -A
git status
git commit -m "v0.5: project(send_files), prompt send!=read, file(write) without content, DEPLOY-v0.5"
git push -u origin main
```

Пояснение:
- `git init` — создаёт репозиторий в папке `gigabot`.
- `git remote add origin ...` — привязывает удалённый репозиторий.
- `git fetch` + `git reset --soft origin/main` — подтягивает историю с GitHub и выставляет текущее состояние ветки `main`, не трогая файлы (твои правки остаются в индексе).
- `git add -A` — добавляет все изменения.
- `git push` — отправляет коммит на GitHub.

---

## Вариант 2: Если у тебя уже есть клон репозитория в другом месте

Если gigabot уже клонирован (есть папка с `.git`):

```powershell
cd "путь\к\клону\gigabot"
git pull origin main
```

Скопируй в этот клон изменённые файлы из `nanobot-main\gigabot`:
- `gigabot/agent/tools/filesystem.py`
- `gigabot/agent/context.py`
- `docs/DEPLOY-v0.5.md`
- `docs/WORK-PLAN-v0.5-done.md`

Затем:

```powershell
git add -A
git commit -m "v0.5: project(send_files), prompt, file(write) without content, deploy doc"
git push origin main
```

---

## Если Git просит логин/пароль при push

GitHub не принимает пароль по HTTPS. Варианты:

1. **Personal Access Token (рекомендуется)**  
   На GitHub: Settings → Developer settings → Personal access tokens → создать токен с правом `repo`. При `git push` в качестве пароля вставь этот токен.

2. **SSH**  
   Настроить ключ и использовать URL вида `git@github.com:SoapMaker101/gigabot.git`:
   ```powershell
   git remote set-url origin git@github.com:SoapMaker101/gigabot.git
   git push -u origin main
   ```
