from __future__ import annotations

import argparse
import logging
import threading
import time
from pathlib import Path
from typing import Any

from medaudit_diff_watcher.ai_client import AISummaryClient
from medaudit_diff_watcher.compare_tool_launcher import CompareToolLauncher
from medaudit_diff_watcher.config import AppConfig, WatchScope, expand_watch_scopes, load_config
from medaudit_diff_watcher.csv_diff import CsvDiffEngine
from medaudit_diff_watcher.doctor import run_doctor
from medaudit_diff_watcher.pipeline import PipelineRunner
from medaudit_diff_watcher.planner import JobPlanner
from medaudit_diff_watcher.reporting import DetailedReportRenderer
from medaudit_diff_watcher.repository import DiffRepository
from medaudit_diff_watcher.stability import FolderStabilityChecker
from medaudit_diff_watcher.watcher import WatcherService


def _setup_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _build_pipeline(config: AppConfig) -> PipelineRunner:
    planner = JobPlanner(config)
    repo = DiffRepository(config.db.sqlite_path)
    diff_engine = CsvDiffEngine(config.csv, config.diff)
    compare_tool_launcher = CompareToolLauncher(config.compare_tool)
    renderer = DetailedReportRenderer(config.report.output_dir)
    ai_client = AISummaryClient(config.ai)
    return PipelineRunner(
        planner=planner,
        repo=repo,
        diff_engine=diff_engine,
        compare_tool_launcher=compare_tool_launcher,
        report_renderer=renderer,
        ai_client=ai_client,
    )


def _build_watch_pipelines(config: AppConfig) -> list[tuple[str, PipelineRunner]]:
    scopes = expand_watch_scopes(config)
    return [(scope.name, _build_pipeline(scope.config)) for scope in scopes]


def _build_watch_scopes(config: AppConfig) -> list[WatchScope]:
    scopes = expand_watch_scopes(config)
    if not scopes:
        raise RuntimeError("No watch roots configured. Set watch.root_dir or watch.root_dirs.")
    return scopes


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medaudit-diff-watcher")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run the long-lived watcher service")
    sub.add_parser("scan-once", help="Scan once and trigger one comparison if applicable")

    compare = sub.add_parser("compare", help="Manual compare two folders")
    compare.add_argument("--left", required=True, help="Left folder path")
    compare.add_argument("--right", required=True, help="Right folder path")
    compare.add_argument("--watch-name", help="Target watch scope name (multi-watch config only)")

    rebuild = sub.add_parser("rebuild-report", help="Rebuild reports from database for a job")
    rebuild.add_argument("--job-id", required=True, type=int, help="Job ID")
    rebuild.add_argument("--watch-name", help="Target watch scope name (recommended for multi-watch config)")

    sub.add_parser("doctor", help="Validate config and environment")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    _setup_logging(config.logging.level)
    logger = logging.getLogger("medaudit_diff_watcher")

    if args.command == "doctor":
        scopes = _build_watch_scopes(config)
        failed = False
        for scope in scopes:
            checks = run_doctor(scope.config)
            for check in checks:
                status = "OK" if check.ok else "FAIL"
                print(f"[{scope.name}] [{status}] {check.name}: {check.detail}")
                failed = failed or not check.ok
        return 1 if failed else 0

    if args.command == "scan-once":
        any_processed = False
        for watch_name, pipeline in _build_watch_pipelines(config):
            job_ids = pipeline.process_latest_pairs(trigger_reason="scan_once")
            if not job_ids:
                print(f"[{watch_name}] No comparison pair available yet.")
                continue
            any_processed = True
            batch_slug = pipeline.last_batch_result.batch_slug if pipeline.last_batch_result else "(unknown-batch)"
            print(f"[{watch_name}] Processed batch {batch_slug} (jobs: {', '.join(str(i) for i in job_ids)})")
        if not any_processed:
            return 0
        return 0

    if args.command == "compare":
        watch_name, pipeline = _select_single_pipeline(config, watch_name=getattr(args, "watch_name", None))
        job_ids = pipeline.process_manual_pairs(args.left, args.right, trigger_reason="manual_cli")
        batch_slug = pipeline.last_batch_result.batch_slug if pipeline.last_batch_result else "(unknown-batch)"
        print(f"[{watch_name}] Processed batch {batch_slug} (jobs: {', '.join(str(i) for i in job_ids)})")
        return 0

    if args.command == "rebuild-report":
        watch_name, pipeline = _select_pipeline_for_rebuild(
            config,
            job_id=args.job_id,
            watch_name=getattr(args, "watch_name", None),
        )
        paths = pipeline.rebuild_reports(args.job_id)
        for report_type, path in paths.items():
            print(f"[{watch_name}] {report_type}: {path}")
        return 0

    if args.command == "run":
        scopes = _build_watch_scopes(config)
        services: list[WatcherService] = []
        threads: list[threading.Thread] = []

        for scope in scopes:
            pipeline = _build_pipeline(scope.config)
            planner = pipeline.planner
            stability = FolderStabilityChecker(scope.config.watch.stable_wait_sec)

            def _make_on_trigger(watch_name: str, runner: PipelineRunner):
                def _on_trigger(reason: str) -> None:
                    try:
                        job_ids = runner.process_latest_pairs(trigger_reason=reason)
                        if job_ids:
                            batch_slug = (
                                runner.last_batch_result.batch_slug if runner.last_batch_result else "(unknown-batch)"
                            )
                            logger.info("[%s] Processed batch %s jobs %s via trigger=%s", watch_name, batch_slug, job_ids, reason)
                    except FileNotFoundError as exc:
                        logger.warning("[%s] Skipped trigger=%s: %s", watch_name, reason, exc)
                    except Exception:
                        logger.exception("[%s] Failed processing trigger=%s", watch_name, reason)

                return _on_trigger

            service = WatcherService(
                planner=planner,
                stability_checker=stability,
                on_trigger=_make_on_trigger(scope.name, pipeline),
                scan_interval_sec=scope.config.watch.scan_interval_sec,
            )
            services.append(service)
            thread = threading.Thread(
                target=_run_service_thread,
                args=(service, scope.name, logger),
                daemon=False,
                name=f"watcher-{scope.name}",
            )
            threads.append(thread)

        for scope in scopes:
            logger.info(
                "Starting watcher[%s] on %s (db=%s, reports=%s)",
                scope.name,
                Path(scope.config.watch.root_dir).expanduser(),
                Path(scope.config.db.sqlite_path).expanduser(),
                Path(scope.config.report.output_dir).expanduser(),
            )

        try:
            for t in threads:
                t.start()
            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Stopping watcher (Ctrl+C)")
            for service in services:
                service.stop()
            for t in threads:
                t.join(timeout=5)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run_service_thread(service: WatcherService, watch_name: str, logger: logging.Logger) -> None:
    try:
        service.run()
    except Exception:
        logger.exception("[%s] Watcher service crashed", watch_name)


def _select_single_pipeline(config: AppConfig, *, watch_name: str | None = None) -> tuple[str, PipelineRunner]:
    pipelines = _build_watch_pipelines(config)
    if not pipelines:
        raise RuntimeError("No watch roots configured.")
    if watch_name:
        for name, pipeline in pipelines:
            if name == watch_name:
                return name, pipeline
        available = ", ".join(name for name, _ in pipelines)
        raise KeyError(f"Unknown watch-name '{watch_name}'. Available: {available}")
    if len(pipelines) > 1:
        logging.getLogger("medaudit_diff_watcher").warning(
            "Multi-watch config detected; --watch-name not provided. Using first scope: %s",
            pipelines[0][0],
        )
    return pipelines[0]


def _select_pipeline_for_rebuild(
    config: AppConfig,
    *,
    job_id: int,
    watch_name: str | None = None,
) -> tuple[str, PipelineRunner]:
    pipelines = _build_watch_pipelines(config)
    if watch_name:
        for name, pipeline in pipelines:
            if name == watch_name:
                return name, pipeline
        available = ", ".join(name for name, _ in pipelines)
        raise KeyError(f"Unknown watch-name '{watch_name}'. Available: {available}")

    matches: list[tuple[str, PipelineRunner]] = []
    for name, pipeline in pipelines:
        if pipeline.repo.get_job(job_id):
            matches.append((name, pipeline))

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(name for name, _ in matches)
        raise RuntimeError(
            f"Job ID {job_id} exists in multiple watch DBs ({names}). Please specify --watch-name."
        )
    raise KeyError(f"Job ID {job_id} not found in any configured watch DB.")
