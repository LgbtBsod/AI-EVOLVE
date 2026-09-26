#!/usr/bin/env python3
"""Пул подпроцессов для QA: много прогонов игры/тестов разом.

Каждый прогон игры - отдельный процесс (ShowBase - синглтон, а свежий процесс
гарантирует детерминизм), поэтому параллелизм - процессный: ThreadPoolExecutor
на `jobs` одновременных подпроцессов (по умолчанию - число ядер). Потоки только ждут
ввода-вывода детей; таймаут убивает всё дерево процессов.

    results = run_many([Job("a", [sys.executable, "tools/agent_play.py", ...]), ...], jobs=4)
    for r in results: r.name, r.rc, r.stdout, r.seconds

run_many() сохраняет порядок входа; первый упавший не отменяет остальные
(для фаззинга и Monte Carlo нужны все результаты). stop_when(result) -> True
позволяет прервать хвост очереди (ddmin: хватит одного воспроизведения).
"""
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Job:
    name: str
    argv: list
    env: dict = field(default_factory=dict)
    timeout: float = 600.0
    meta: dict = field(default_factory=dict)


@dataclass
class Result:
    name: str
    rc: int
    stdout: str
    stderr: str
    seconds: float
    meta: dict
    skipped: bool = False

    @property
    def ok(self):
        return self.rc == 0


def default_jobs():
    return max(1, (os.cpu_count() or 2))


def _kill_tree(proc):
    """Kill the child and (on Windows) its process tree."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    proc.kill()


def _run_one(job, cancelled):
    if cancelled.is_set():
        return Result(job.name, -1, "", "", 0.0, job.meta, skipped=True)
    start = time.perf_counter()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **job.env}
    proc = subprocess.Popen(job.argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=job.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, err = proc.communicate()
        rc = 124
        err += f"\n[qa_pool] timeout after {job.timeout}s".encode()
    return Result(job.name, rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"),
                  time.perf_counter() - start, job.meta)


def run_many(jobs_list, jobs=None, stop_when=None):
    jobs_list = list(jobs_list)
    if not jobs_list:
        return []
    from concurrent.futures import ThreadPoolExecutor  # lazy: pulls logging (~30 ms) that brief/ctx/find never need

    cancelled = threading.Event()

    def guarded(job):
        result = _run_one(job, cancelled)
        if stop_when is not None and not result.skipped and stop_when(result):
            cancelled.set()
        return result

    with ThreadPoolExecutor(max_workers=max(1, jobs or default_jobs())) as pool:
        return list(pool.map(guarded, jobs_list))


def python_job(name, script, *args, **kw):
    """Job для `python <script> args...` тем же интерпретатором."""
    return Job(name, [sys.executable, str(script), *map(str, args)], **kw)
