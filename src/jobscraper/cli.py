"""Command-line interface for the assisted job workflow."""

from __future__ import annotations

import dataclasses
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .browser.autofill import autofill_job
from .config import Config, find_project_root, load_environment
from .core.questionParse import (
    approve_question,
    draft_answers,
    scan_questions,
    set_answer,
    skip_question,
)
from .core.questionSubmit import generate_packet, track_application, update_application
from .core.updateData import refresh_statuses
from .core.webscraper import collect_jobs, refilter_jobs
from .llm.factory import build_provider, resolve_settings
from .models import ApplicationStatus, JobStatus, parse_job_status
from .services.doctor import run_doctor
from .services.init import initialize_project
from .sources.config import SourcesConfig
from .storage.applications import ApplicationStore
from .storage.jobs import JobStore
from .storage.questions import BankStore, QuestionStore
from .utils.errors import ConfigError, JobscraperError
from .utils.http import HttpClient
from .utils.logging import configure_logging

console = Console()
app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    add_completion=False,
    help="Assisted job discovery, answer preparation, and form autofill.",
)
jobs_app = typer.Typer(no_args_is_help=True, help="Inspect and refresh discovered jobs.")
questions_app = typer.Typer(no_args_is_help=True, help="Scan, draft, and approve answers.")
bank_app = typer.Typer(no_args_is_help=True, help="Inspect the reusable answer bank.")
applications_app = typer.Typer(no_args_is_help=True, help="Track submitted applications.")
config_app = typer.Typer(no_args_is_help=True, help="Show resolved configuration.")
app.add_typer(jobs_app, name="jobs")
app.add_typer(questions_app, name="questions")
questions_app.add_typer(bank_app, name="bank")
app.add_typer(applications_app, name="applications")
app.add_typer(config_app, name="config")

log = logging.getLogger(__name__)


@app.callback()
def _main_callback(
    ctx: typer.Context,
    root: Path | None = typer.Option(
        None,
        "--root",
        help="Project root containing user/. Defaults to upward search from the cwd.",
        show_default=False,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs."),
    version: bool = typer.Option(
        False, "--version", help="Show the jobscraper version and exit.", is_eager=True
    ),
) -> None:
    if version:
        console.print(f"jobscraper {__version__}")
        raise typer.Exit()
    configure_logging(verbose)
    ctx.obj = {"root": root, "verbose": verbose}


def _config(ctx: typer.Context) -> Config:
    data = ctx.obj or {}
    root = data.get("root")
    resolved = (root or find_project_root()).expanduser().resolve()
    load_environment(resolved)
    return Config.load(resolved)


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, default=_json_default, ensure_ascii=False))


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return str(value)


@app.command()
def init(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing user files (backups kept)."
    ),
) -> None:
    """Create user configs, a starter resume, .env.local, and empty CSV tables."""
    data = ctx.obj or {}
    root = (data.get("root") or find_project_root()).expanduser().resolve()
    written = initialize_project(root, force=force)
    console.print(f"Initialized project at [bold]{root}[/bold]")
    for path in dict.fromkeys(written):
        console.print(
            f"  [green]✓[/green] {path.relative_to(root) if path.is_relative_to(root) else path}"
        )
    console.print(
        "\nNext: edit [bold].env.local[/bold], [bold]user/user.toml[/bold], and "
        "[bold]user/urls.yaml[/bold], then run [bold]uv run jobscraper doctor[/bold]."
    )


@app.command()
def doctor(
    ctx: typer.Context,
    check_llm: bool = typer.Option(
        False, "--check-llm", help="Send a tiny request to the provider."
    ),
) -> None:
    """Validate configuration, tables, resume, LLM, and browser availability."""
    config = _config(ctx)
    checks = run_doctor(config, check_llm=check_llm)
    table = Table(title="jobscraper doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    failed = False
    for check in checks:
        if not check.ok:
            failed = True
            status = "[red]FAIL[/red]"
        elif check.warning:
            status = "[yellow]WARN[/yellow]"
        else:
            status = "[green]OK[/green]"
        table.add_row(check.name, status, check.detail)
    console.print(table)
    if failed:
        raise typer.Exit(1)


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Print the resolved configuration with secrets masked."""
    config = _config(ctx)
    payload = config.model_dump(mode="json")
    settings = resolve_settings(config)
    payload["resolved_llm"] = {
        "provider": settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
        "api_key": "***" if settings.api_key else "",
    }
    payload["resolved_season"] = config.season
    _print_json(payload)


@app.command()
def collect(
    ctx: typer.Context,
    source: list[str] = typer.Option(
        [],
        "--source",
        help="Limit to a source name (repeatable): greenhouse, lever, arbeitnow, remoteok, generic.",
    ),
    limit: int | None = typer.Option(None, "--limit", help="Max postings inspected this run."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch and report without writing tables."
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable summary."),
) -> None:
    """Fetch, normalize, keyword-filter, and store job postings."""
    config = _config(ctx)
    sources = SourcesConfig.load(config.urls_path)
    report = collect_jobs(
        config,
        sources,
        limit=limit,
        source_names=source,
        dry_run=dry_run,
    )
    if json_output:
        _print_json(dataclasses.asdict(report))
        return
    label = "Dry run" if report.dry_run else "Collected"
    console.print(
        f"{label}: [bold]{report.discovered}[/bold] discovered, "
        f"[green]{report.added}[/green] new, "
        f"[cyan]{report.updated}[/cyan] updated, "
        f"[yellow]{report.filtered_out}[/yellow] filtered out."
    )
    for error in report.errors:
        console.print(f"[yellow]Source warning:[/yellow] {error}")


@app.command()
def filter(ctx: typer.Context) -> None:  # noqa: A001 - matches the workflow vocabulary
    """Re-apply include/disclude keywords to jobs that are not applied."""
    config = _config(ctx)
    kept, filtered = refilter_jobs(config)
    console.print(
        f"Filters applied: [green]{kept}[/green] kept, [yellow]{filtered}[/yellow] filtered out."
    )


@jobs_app.command("list")
def jobs_list(
    ctx: typer.Context,
    status: list[str] = typer.Option([], "--status", help="Filter by status (repeatable)."),
    limit: int = typer.Option(30, "--limit", min=1),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List discovered jobs."""
    config = _config(ctx)
    jobs = JobStore.from_config(config).load()
    wanted: set[JobStatus] = set()
    for value in status:
        try:
            wanted.add(parse_job_status(value))
        except ValueError as exc:
            raise ConfigError(f"Unknown status {value!r}") from exc
    if wanted:
        jobs = [job for job in jobs if job.status in wanted]
    jobs = jobs[:limit]
    if json_output:
        _print_json([dataclasses.asdict(job) for job in jobs])
        return
    table = Table(title=f"Jobs ({len(jobs)})")
    table.add_column("Job ID", no_wrap=True)
    table.add_column("Status")
    table.add_column("Company")
    table.add_column("Title", overflow="fold")
    table.add_column("Location")
    table.add_column("Source")
    for job in jobs:
        table.add_row(
            job.job_id,
            job.status.value,
            job.company,
            job.title,
            job.location or "—",
            job.source,
        )
    console.print(table)


@jobs_app.command("show")
def jobs_show(ctx: typer.Context, job_id: str) -> None:
    """Show one job, its questions, and its description excerpt."""
    config = _config(ctx)
    store = JobStore.from_config(config)
    job = store.require(job_id)
    question_store = QuestionStore.from_config(config)
    questions = question_store.for_job(job_id)
    console.print(f"[bold]{job.title}[/bold] — {job.company}")
    console.print(
        f"Status: [bold]{job.status.value}[/bold] · Source: {job.source or '—'} · "
        f"Location: {job.location or '—'}"
    )
    if job.url:
        console.print(f"Posting: {job.url}")
    if job.apply_url:
        console.print(f"Apply: {job.apply_url}")
    if job.tags:
        console.print("Tags: " + ", ".join(job.tags))
    if job.packet_path:
        console.print(f"Packet: {job.packet_path}")
    console.print(f"Questions: {len(questions)}")
    description = store.read_description(job)
    if description:
        console.print("\n[bold]Description[/bold]")
        console.print(description[:4000] + ("…" if len(description) > 4000 else ""))


@jobs_app.command("refresh")
def jobs_refresh(ctx: typer.Context) -> None:
    """Recalculate statuses from questions and applications."""
    config = _config(ctx)
    jobs = refresh_statuses(config)
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status.value] = counts.get(job.status.value, 0) + 1
    summary = ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
    console.print(f"Refreshed {len(jobs)} jobs" + (f" ({summary})" if summary else ""))


@questions_app.command("scan")
def questions_scan(
    ctx: typer.Context,
    job_id: str,
    url: str = typer.Option("", "--url", help="Static application page URL to fetch."),
    html: Path | None = typer.Option(None, "--html", help="Saved form HTML file."),
    ai: bool = typer.Option(False, "--ai/--no-ai", help="Ask the LLM to clean up labels."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Extract application questions from a form URL or saved HTML."""
    config = _config(ctx)
    if bool(url) == bool(html):
        raise ConfigError("Pass exactly one of --url or --html.")
    if html is not None:
        html_text = html.expanduser().read_text(encoding="utf-8")
        source = "html"
    else:
        with HttpClient(
            timeout=config.scraping.timeout,
            retries=config.scraping.retries,
            user_agent=config.scraping.user_agent,
        ) as client:
            html_text = client.get_text(url)
        source = "url"
    use_ai = ai and config.llm.refine_extraction
    questions = scan_questions(
        config,
        job_id,
        html_text,
        source=source,
        use_ai=use_ai,
        provider=build_provider(config) if use_ai else None,
    )
    if json_output:
        _print_json([dataclasses.asdict(question) for question in questions])
        return
    if not questions:
        console.print("[yellow]No application questions found.[/yellow]")
        return
    _render_questions(questions)


@questions_app.command("list")
def questions_list(
    ctx: typer.Context,
    job_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List questions for a job."""
    config = _config(ctx)
    questions = QuestionStore.from_config(config).for_job(job_id)
    if json_output:
        _print_json([dataclasses.asdict(question) for question in questions])
        return
    if not questions:
        console.print("No questions for this job yet.")
        return
    _render_questions(questions)


@questions_app.command("answer")
def questions_answer(
    ctx: typer.Context,
    job_id: str,
    include_existing: bool = typer.Option(
        False, "--include-existing", help="Also redraft needs_review questions."
    ),
) -> None:
    """Draft answers for unanswered questions using the configured LLM."""
    config = _config(ctx)
    provider = build_provider(config)
    questions = draft_answers(config, job_id, provider=provider, include_existing=include_existing)
    pending = [question for question in questions if question.answer.strip()]
    console.print(
        f"Drafted [green]{len(pending)}[/green] answers. "
        "Nothing is approved automatically; review with `questions list`."
    )
    _render_questions(questions)


@questions_app.command("set")
def questions_set(
    ctx: typer.Context,
    question_id: str,
    answer: str = typer.Option(..., "--answer", "-a", help="Approved answer text."),
    draft: bool = typer.Option(False, "--draft", help="Save as needs_review instead of approving."),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Set an answer and, when approved, update the reusable bank."""
    config = _config(ctx)
    question, bank = set_answer(config, question_id, answer, approve=not draft, notes=notes)
    console.print(
        f"Saved {question.question_id} as [bold]{question.status.value}[/bold]"
        + (f" (bank {bank.answer_id})" if bank else "")
    )


@questions_app.command("approve")
def questions_approve(ctx: typer.Context, question_id: str) -> None:
    """Approve the current answer on a question."""
    config = _config(ctx)
    question = approve_question(config, question_id)
    console.print(f"Approved {question.question_id}.")


@questions_app.command("skip")
def questions_skip(ctx: typer.Context, question_id: str) -> None:
    """Mark a question as intentionally skipped."""
    config = _config(ctx)
    question = skip_question(config, question_id)
    console.print(f"Skipped {question.question_id}.")


@bank_app.command("list")
def bank_list(
    ctx: typer.Context,
    query: str = typer.Argument("", help="Filter by question, answer, category, or status."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List reusable answers."""
    config = _config(ctx)
    answers = BankStore.from_config(config).load()
    if query:
        needle = query.casefold()
        answers = [
            answer
            for answer in answers
            if needle
            in " ".join(
                [
                    answer.question,
                    answer.answer,
                    answer.category,
                    answer.job_type,
                    answer.job_field,
                    answer.status.value,
                ]
            ).casefold()
        ]
    if json_output:
        _print_json([dataclasses.asdict(answer) for answer in answers])
        return
    table = Table(title=f"Answer bank ({len(answers)})")
    table.add_column("Answer ID", no_wrap=True)
    table.add_column("Status")
    table.add_column("Question", overflow="fold")
    table.add_column("Answer", overflow="fold")
    table.add_column("Used", justify="right")
    for answer in answers:
        table.add_row(
            answer.answer_id,
            answer.status.value,
            answer.question,
            answer.answer[:160] + ("…" if len(answer.answer) > 160 else ""),
            str(answer.times_used),
        )
    console.print(table)


@app.command()
def packet(
    ctx: typer.Context,
    job_id: str,
    out: Path | None = typer.Option(None, "--out", help="Output directory override."),
) -> None:
    """Generate a reviewable Markdown application packet."""
    config = _config(ctx)
    path = generate_packet(config, job_id, out_dir=out)
    console.print(f"Packet written to [bold]{path}[/bold]")


@app.command()
def autofill(
    ctx: typer.Context,
    job_id: str,
    url: str = typer.Option("", "--url", help="Override the job application URL."),
    fill: bool = typer.Option(False, "--fill", help="Actually fill the form. Never submits."),
    headless: bool | None = typer.Option(None, "--headless/--no-headless"),
    keep_open: bool | None = typer.Option(None, "--keep-open/--no-keep-open"),
    save_questions: bool = typer.Option(
        False, "--save-questions", help="Persist fields as questions."
    ),
    include_drafts: bool | None = typer.Option(None, "--include-drafts/--approved-only"),
    screenshot: Path | None = typer.Option(
        None, "--screenshot", help="Save a full-page screenshot."
    ),
    timeout_ms: int | None = typer.Option(None, "--timeout-ms", min=1000),
) -> None:
    """Open a form, optionally fill saved answers, and leave submission to you."""
    config = _config(ctx)
    report = autofill_job(
        config,
        job_id,
        url=url,
        fill=fill,
        headless=headless,
        keep_open=keep_open,
        save_questions=save_questions,
        include_drafts=include_drafts,
        screenshot=screenshot,
        timeout_ms=timeout_ms,
    )
    table = Table(title=f"Autofill plan ({report.url})")
    table.add_column("Field", overflow="fold")
    table.add_column("Action")
    table.add_column("Answer", overflow="fold")
    table.add_column("Status")
    for plan in report.plans:
        status = "[green]filled[/green]" if plan.applied else (plan.reason or "planned")
        table.add_row(plan.label, plan.action.value, plan.answer[:120], status)
    console.print(table)
    if report.saved_questions:
        console.print(f"Saved {report.saved_questions} questions.")
    if fill:
        console.print(
            f"Filled [green]{report.applied}[/green] of {len(report.plans)} fields. "
            "Review the browser and click submit yourself — jobscraper never submits."
        )
    else:
        console.print(
            "Dry run only. Add --fill to populate the form (submission is never automated)."
        )
    if report.screenshot:
        console.print(f"Screenshot: {report.screenshot}")


@app.command()
def track(
    ctx: typer.Context,
    job_id: str,
    status: str = typer.Option(
        "applied", "--status", help="applied, interview, rejected, offer, withdrawn"
    ),
    notes: str = typer.Option("", "--notes"),
    force: bool = typer.Option(False, "--force", help="Bypass the same-season duplicate guard."),
) -> None:
    """Record an application and prevent duplicates within the hiring season."""
    config = _config(ctx)
    try:
        application_status = ApplicationStatus(status.casefold())
    except ValueError as exc:
        raise ConfigError(
            "Status must be one of: applied, interview, rejected, offer, withdrawn."
        ) from exc
    application = track_application(
        config, job_id, status=application_status, notes=notes, force=force
    )
    console.print(
        f"Recorded [bold]{application.application_id}[/bold] "
        f"({application.company} — {application.title}, season {application.season})"
    )


@applications_app.command("list")
def applications_list(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List recorded applications."""
    config = _config(ctx)
    applications = ApplicationStore.from_config(config).load()
    if json_output:
        _print_json([dataclasses.asdict(application) for application in applications])
        return
    table = Table(title=f"Applications ({len(applications)})")
    table.add_column("Application ID", no_wrap=True)
    table.add_column("Status")
    table.add_column("Company")
    table.add_column("Title", overflow="fold")
    table.add_column("Season")
    table.add_column("Applied")
    for application in applications:
        table.add_row(
            application.application_id,
            application.status.value,
            application.company,
            application.title,
            application.season,
            application.applied_at,
        )
    console.print(table)


@applications_app.command("update")
def applications_update(
    ctx: typer.Context,
    application_id: str,
    status: str = typer.Option("", "--status", help="New application status."),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Update an application's status or notes (interviews, rejections, offers)."""
    config = _config(ctx)
    if not status and not notes:
        raise ConfigError("Pass --status and/or --notes.")
    parsed: ApplicationStatus | None = None
    if status:
        try:
            parsed = ApplicationStatus(status.casefold())
        except ValueError as exc:
            raise ConfigError(
                "Status must be one of: applied, interview, rejected, offer, withdrawn."
            ) from exc
    application = update_application(config, application_id, status=parsed, notes=notes)
    console.print(f"Updated {application.application_id} to {application.status.value}.")


def _render_questions(questions: list[Any]) -> None:
    table = Table(title=f"Questions ({len(questions)})")
    table.add_column("Question ID", no_wrap=True)
    table.add_column("Status")
    table.add_column("Kind")
    table.add_column("Question", overflow="fold")
    table.add_column("Answer", overflow="fold")
    for question in questions:
        answer = (question.answer or "").strip()
        table.add_row(
            question.question_id,
            question.status.value,
            question.kind.value,
            question.question,
            answer[:160] + ("…" if len(answer) > 160 else "") if answer else "—",
        )
    console.print(table)


def main() -> None:
    """Console-script entry point with concise error handling."""
    try:
        app()
    except JobscraperError as exc:
        Console(stderr=True).print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":  # pragma: no cover
    main()
