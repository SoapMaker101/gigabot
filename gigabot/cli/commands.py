"""CLI-команды GigaBot."""

import asyncio
import os
import signal
from pathlib import Path
import select
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from gigabot import __version__, __logo__
from gigabot.config.schema import Config

app = typer.Typer(
    name="gigabot",
    help=f"{__logo__} GigaBot — AI-агент на базе GigaChat",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q", "выход"}

# ---------------------------------------------------------------------------
# Ввод из CLI: prompt_toolkit для редактирования, вставки, истории
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None


def _flush_pending_tty_input() -> None:
    """Сбросить непрочитанные нажатия клавиш, набранные пока модель генерировала ответ."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Восстановить терминал в исходное состояние."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Создать prompt_toolkit сессию с файловой историей."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".gigabot" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Вывести ответ ассистента с единообразным оформлением."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} GigaBot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Вернуть True, если ввод завершает интерактивный чат."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Чтение ввода пользователя через prompt_toolkit (вставка, история, отображение)."""
    if _PROMPT_SESSION is None:
        raise RuntimeError("Сначала вызовите _init_prompt_session()")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>Вы:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} GigaBot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """GigaBot — AI-агент на базе GigaChat."""
    pass


# ============================================================================
# Утилита: создание провайдера
# ============================================================================


def _make_provider(config: Config):
    """Создать GigaChatProvider из конфигурации.

    Если credentials не заданы, выводит ошибку и завершает работу.
    """
    from gigabot.providers.gigachat_provider import GigaChatProvider

    if not config.gigachat.credentials:
        console.print("[red]Ошибка: GigaChat credentials не заданы.[/red]")
        console.print(
            "Укажите их в [cyan]~/.gigabot/config.json[/cyan] "
            'в разделе [bold]"gigachat" → "credentials"[/bold].'
        )
        console.print(
            "\nПолучить авторизационные данные: "
            "[link=https://developers.sber.ru/portal/products/gigachat-api]"
            "developers.sber.ru[/link]"
        )
        raise typer.Exit(1)

    return GigaChatProvider(
        credentials=config.gigachat.credentials,
        scope=config.gigachat.scope,
        model=config.gigachat.model,
        verify_ssl_certs=config.gigachat.verify_ssl_certs,
        timeout=config.gigachat.timeout,
    )


# ============================================================================
# Onboard / Настройка
# ============================================================================


@app.command()
def onboard():
    """Инициализировать конфигурацию и рабочее пространство GigaBot."""
    from gigabot.config.loader import get_config_path, load_config, save_config
    from gigabot.config.schema import Config
    from gigabot.utils.helpers import get_workspace_path

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Конфиг уже существует: {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = сбросить к настройкам по умолчанию (текущие значения будут потеряны)")
        console.print("  [bold]N[/bold] = обновить конфиг, сохранив существующие значения и добавив новые поля")
        if typer.confirm("Перезаписать?"):
            config = Config()
            save_config(config)
            console.print(f"[green]✓[/green] Конфиг сброшен к умолчаниям: {config_path}")
        else:
            config = load_config()
            save_config(config)
            console.print(f"[green]✓[/green] Конфиг обновлён: {config_path} (существующие значения сохранены)")
    else:
        save_config(Config())
        console.print(f"[green]✓[/green] Создан конфиг: {config_path}")

    workspace = get_workspace_path()

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Создано рабочее пространство: {workspace}")

    _create_workspace_directories(workspace)
    _create_workspace_templates(workspace)

    console.print(f"\n{__logo__} GigaBot готов к работе!")
    console.print("\nСледующие шаги:")
    console.print("  1. Отредактируйте [cyan]~/.gigabot/config.json[/cyan]")
    console.print("     Добавьте GigaChat credentials: [link=https://developers.sber.ru/portal/products/gigachat-api]developers.sber.ru[/link]")
    console.print("  2. Проверьте связь: [cyan]gigabot agent -m \"Привет!\"[/cyan]")
    console.print("  3. Для Telegram-бота: настройте раздел [cyan]\"telegram\"[/cyan] в config.json")


def _create_workspace_directories(workspace: Path):
    """Создать стандартные каталоги рабочего пространства."""
    dirs = ["memory", "projects", "skills"]
    for name in dirs:
        d = workspace / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            console.print(f"  [dim]Создан каталог {name}/[/dim]")


def _create_workspace_templates(workspace: Path):
    """Создать шаблонные файлы рабочего пространства."""
    templates = {
        "AGENTS.md": """\
# Инструкции агента

Ты — GigaBot, AI-ассистент на базе GigaChat.
Отвечай на русском языке. Будь точным, лаконичным и дружелюбным.

## Правила

- Перед действием объясни, что собираешься делать
- Если запрос неоднозначен — уточни
- Используй инструменты для выполнения задач
- Важную информацию сохраняй в memory/MEMORY.md
- Прошлые события записывай в memory/HISTORY.md

## Область ответственности

- Управление файлами и проектами в рабочем пространстве
- Поиск информации в интернете
- Выполнение скриптов и команд
- Планирование и выполнение задач по расписанию
""",
        "SOUL.md": """\
# Душа

Я — GigaBot, AI-помощник на базе GigaChat от Сбера.

## Характер

- Отвечаю на русском языке
- Лаконичный и по делу
- Дружелюбный, но профессиональный
- Люблю помогать с техническими задачами

## Ценности

- Точность важнее скорости
- Конфиденциальность пользователя
- Прозрачность действий
- Если не знаю — честно скажу
""",
        "USER.md": """\
# Пользователь

Информация о пользователе.

## Предпочтения

- Язык: русский
- Стиль общения: (по умолчанию / неформальный / формальный)
- Часовой пояс: (ваш часовой пояс)

## Заметки

(Важные факты о пользователе, узнанные в процессе общения)
""",
    }

    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            console.print(f"  [dim]Создан {filename}[/dim]")

    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""\
# Долговременная память

Этот файл хранит важную информацию между сессиями.

## Информация о пользователе

(Важные факты о пользователе)

## Предпочтения

(Предпочтения пользователя, выявленные в процессе общения)

## Важные заметки

(Что нужно помнить)
""", encoding="utf-8")
        console.print("  [dim]Создан memory/MEMORY.md[/dim]")

    history_file = memory_dir / "HISTORY.md"
    if not history_file.exists():
        history_file.write_text("", encoding="utf-8")
        console.print("  [dim]Создан memory/HISTORY.md[/dim]")


# ============================================================================
# Gateway / Сервер
# ============================================================================


@app.command()
def gateway(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Подробный вывод логов"),
):
    """Запустить полный сервер GigaBot с Telegram-каналом."""
    from gigabot.config.loader import load_config, get_data_dir
    from gigabot.bus.queue import MessageBus
    from gigabot.agent.loop import AgentLoop
    from gigabot.channels.manager import ChannelManager
    from gigabot.session.manager import SessionManager
    from gigabot.cron.service import CronService
    from gigabot.cron.types import CronJob
    from gigabot.heartbeat.service import HeartbeatService

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} Запуск GigaBot gateway...")

    config = load_config()
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.gigachat.model,
        temperature=config.gigachat.temperature,
        max_tokens=config.gigachat.max_tokens,
        max_iterations=config.agent.max_tool_iterations,
        memory_window=config.agent.memory_window,
        brave_api_key=config.tools.web.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        rag_config=config.rag,
        salute_speech_config=config.salute_speech,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        """Выполнить задачу cron через агента."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from gigabot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response or "",
            ))
        return response

    cron.on_job = on_cron_job

    async def on_heartbeat(prompt: str) -> str:
        """Выполнить heartbeat через агента."""
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,
        enabled=True,
    )

    channels = ChannelManager(config, bus)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Каналы: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Внимание: ни один канал не включён[/yellow]")
        console.print("  Настройте Telegram в [cyan]~/.gigabot/config.json[/cyan]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} запланированных задач")

    console.print("[green]✓[/green] Heartbeat: каждые 30 мин")
    console.print(f"[green]✓[/green] Модель: {config.gigachat.model}")

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nОстановка...")
        finally:
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Агент: интерактивный и однократный режим
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Сообщение для агента"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="ID сессии"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Рендерить ответ как Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Показывать логи GigaBot"),
):
    """Взаимодействие с агентом напрямую."""
    from gigabot.config.loader import load_config, get_data_dir
    from gigabot.bus.queue import MessageBus
    from gigabot.agent.loop import AgentLoop
    from gigabot.cron.service import CronService
    from loguru import logger

    config = load_config()

    bus = MessageBus()
    provider = _make_provider(config)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("gigabot")
    else:
        logger.disable("gigabot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.gigachat.model,
        temperature=config.gigachat.temperature,
        max_tokens=config.gigachat.max_tokens,
        max_iterations=config.agent.max_tool_iterations,
        memory_window=config.agent.memory_window,
        brave_api_key=config.tools.web.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        rag_config=config.rag,
        salute_speech_config=config.salute_speech,
    )

    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        return console.status("[dim]GigaBot думает...[/dim]", spinner="dots")

    async def _cli_progress(content: str) -> None:
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(
                    message, session_id, on_progress=_cli_progress,
                )
            _print_agent_response(response, render_markdown=markdown)

        asyncio.run(run_once())
    else:
        from gigabot.bus.events import InboundMessage
        _init_prompt_session()
        console.print(
            f"{__logo__} Интерактивный режим "
            "(введите [bold]выход[/bold] или [bold]Ctrl+C[/bold] для завершения)\n"
        )

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nДо свидания!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nДо свидания!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nДо свидания!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nДо свидания!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)

        asyncio.run(run_interactive())


# ============================================================================
# Статус
# ============================================================================


@app.command()
def status():
    """Показать статус GigaBot."""
    from gigabot.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} Статус GigaBot\n")

    console.print(
        f"Конфиг: {config_path} "
        f"{'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
    )
    console.print(
        f"Рабочее пространство: {workspace} "
        f"{'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
    )
    console.print(f"Модель: {config.gigachat.model}")

    has_creds = bool(config.gigachat.credentials)
    console.print(
        f"GigaChat credentials: "
        f"{'[green]✓ заданы[/green]' if has_creds else '[red]✗ не заданы[/red]'}"
    )
    console.print(f"Scope: {config.gigachat.scope}")
    console.print(f"Температура: {config.gigachat.temperature}")
    console.print(f"Макс. токены: {config.gigachat.max_tokens}")
    console.print(f"Таймаут: {config.gigachat.timeout}с")
    console.print(f"SSL проверка: {'да' if config.gigachat.verify_ssl_certs else 'нет'}")

    console.print()
    tg = config.telegram
    tg_status = "[green]✓ включён[/green]" if tg.enabled else "[dim]выключен[/dim]"
    console.print(f"Telegram: {tg_status}")
    if tg.token:
        masked = tg.token[:10] + "..." if len(tg.token) > 10 else "[dim]не задан[/dim]"
        console.print(f"  Токен: {masked}")
    if tg.allow_from:
        console.print(f"  Разрешённые пользователи: {', '.join(tg.allow_from)}")

    console.print()
    ss = config.salute_speech
    has_speech = bool(ss.credentials)
    console.print(
        f"SaluteSpeech: "
        f"{'[green]✓ настроен[/green]' if has_speech else '[dim]не настроен[/dim]'}"
    )

    console.print()
    console.print(f"Ограничение файлов рабочим пространством: "
                  f"{'да' if config.tools.restrict_to_workspace else 'нет'}")
    if config.tools.web.api_key:
        console.print("[green]✓[/green] Brave Search API: настроен")


# ============================================================================
# Каналы
# ============================================================================


channels_app = typer.Typer(help="Управление каналами")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Показать статус Telegram-канала."""
    from gigabot.config.loader import load_config

    config = load_config()

    table = Table(title="Статус каналов")
    table.add_column("Канал", style="cyan")
    table.add_column("Статус", style="green")
    table.add_column("Конфигурация", style="yellow")

    tg = config.telegram
    tg_config_str = f"token: {tg.token[:10]}..." if tg.token else "[dim]не настроен[/dim]"
    table.add_row(
        "Telegram",
        "✓ включён" if tg.enabled else "✗ выключен",
        tg_config_str,
    )

    if tg.allow_from:
        table.add_row("", "", f"allow_from: {', '.join(tg.allow_from)}")
    if tg.proxy:
        table.add_row("", "", f"proxy: {tg.proxy}")

    console.print(table)

    if not tg.enabled:
        console.print(
            "\n[dim]Чтобы включить Telegram, установите "
            "[cyan]\"telegram.enabled\": true[/cyan] "
            "и [cyan]\"telegram.token\"[/cyan] в ~/.gigabot/config.json[/dim]"
        )


# ============================================================================
# Cron — управление расписанием
# ============================================================================


cron_app = typer.Typer(help="Управление задачами по расписанию")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Показать отключённые задачи"),
):
    """Список запланированных задач."""
    from gigabot.config.loader import get_data_dir
    from gigabot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("Нет запланированных задач.")
        return

    table = Table(title="Запланированные задачи")
    table.add_column("ID", style="cyan")
    table.add_column("Название")
    table.add_column("Расписание")
    table.add_column("Статус")
    table.add_column("Следующий запуск")

    import time
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    for job in jobs:
        if job.schedule.kind == "every":
            sched = f"каждые {(job.schedule.every_ms or 0) // 1000} сек"
        elif job.schedule.kind == "cron":
            sched = f"{job.schedule.expr or ''}"
            if job.schedule.tz:
                sched += f" ({job.schedule.tz})"
        else:
            sched = "одноразовая"

        next_run = ""
        if job.state.next_run_at_ms:
            ts = job.state.next_run_at_ms / 1000
            try:
                tz = ZoneInfo(job.schedule.tz) if job.schedule.tz else None
                next_run = _dt.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

        status_str = "[green]активна[/green]" if job.enabled else "[dim]отключена[/dim]"

        table.add_row(job.id, job.name, sched, status_str, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Название задачи"),
    message: str = typer.Option(..., "--message", "-m", help="Сообщение для агента"),
    every: int = typer.Option(None, "--every", "-e", help="Запускать каждые N секунд"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron-выражение (например '0 9 * * *')"),
    tz: str | None = typer.Option(None, "--tz", help="Часовой пояс IANA для cron (например 'Europe/Moscow')"),
    at: str = typer.Option(None, "--at", help="Запустить однократно в указанное время (ISO формат)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Доставить ответ в канал"),
    to: str = typer.Option(None, "--to", help="Получатель для доставки"),
    channel: str = typer.Option(None, "--channel", help="Канал для доставки (например 'telegram')"),
):
    """Добавить задачу по расписанию."""
    from gigabot.config.loader import get_data_dir
    from gigabot.cron.service import CronService
    from gigabot.cron.types import CronSchedule

    if tz and not cron_expr:
        console.print("[red]Ошибка: --tz можно использовать только с --cron[/red]")
        raise typer.Exit(1)

    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Ошибка: укажите --every, --cron или --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    try:
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=deliver,
            to=to,
            channel=channel,
        )
    except ValueError as e:
        console.print(f"[red]Ошибка: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]✓[/green] Добавлена задача '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="ID задачи для удаления"),
):
    """Удалить задачу по расписанию."""
    from gigabot.config.loader import get_data_dir
    from gigabot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Задача {job_id} удалена")
    else:
        console.print(f"[red]Задача {job_id} не найдена[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="ID задачи"),
    disable: bool = typer.Option(False, "--disable", help="Отключить вместо включения"),
):
    """Включить или отключить задачу."""
    from gigabot.config.loader import get_data_dir
    from gigabot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        action = "отключена" if disable else "включена"
        console.print(f"[green]✓[/green] Задача '{job.name}' {action}")
    else:
        console.print(f"[red]Задача {job_id} не найдена[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="ID задачи для запуска"),
    force: bool = typer.Option(False, "--force", "-f", help="Запустить даже если отключена"),
):
    """Запустить задачу вручную."""
    from loguru import logger
    from gigabot.config.loader import load_config, get_data_dir
    from gigabot.cron.service import CronService
    from gigabot.cron.types import CronJob
    from gigabot.bus.queue import MessageBus
    from gigabot.agent.loop import AgentLoop

    logger.disable("gigabot")

    config = load_config()
    provider = _make_provider(config)
    bus = MessageBus()

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.gigachat.model,
        temperature=config.gigachat.temperature,
        max_tokens=config.gigachat.max_tokens,
        max_iterations=config.agent.max_tool_iterations,
        memory_window=config.agent.memory_window,
        brave_api_key=config.tools.web.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        rag_config=config.rag,
        salute_speech_config=config.salute_speech,
    )

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    result_holder = []

    async def on_job(job: CronJob) -> str | None:
        response = await agent_loop.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        result_holder.append(response)
        return response

    service.on_job = on_job

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print("[green]✓[/green] Задача выполнена")
        if result_holder:
            _print_agent_response(result_holder[0], render_markdown=True)
    else:
        console.print(f"[red]Не удалось запустить задачу {job_id}[/red]")


# ============================================================================
# Точка входа
# ============================================================================


if __name__ == "__main__":
    app()
