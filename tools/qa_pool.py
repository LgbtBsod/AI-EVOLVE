#!/usr/bin/env python3
"""Асинхронный пул подпроцессов для QA: много прогонов игры/тестов разом.

Каждый прогон игры - отдельный процесс (ShowBase - синглтон, а свежий процесс
гарантирует детерминизм), поэтому параллелизм - процессный: asyncio +
семафор на `jobs` одновременных подпроцессов (по умолчанию - число ядер).
Потоки здесь не помогли бы - работу делают дочерние процессы, а главный
процесс только ждёт их ввода-вывода (для этого asyncio и нужен).

    results = run_many([Job("a", [sys.executable, "tools/agent_play.py", ...]), ...], jobs=4)
    for r in results: r.name, r.rc, r.stdout, r.seconds

run_many() сохраняет порядок входа; первый упавший не отменяет остальные
(для фаззинга и Monte Carlo нужны все результаты). stop_when(result) -> True
позволяет прервать хвост очереди (ddmin: хватит одного воспроизведения).
"""
import asyncio
import os
import sys
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


async def _run_one(job, sem, cancelled):
    async with sem:
        if cancelled.is_set():
            return Result(job.name, -1, "", "", 0.0, job.meta, skipped=True)
        start = time.perf_counter()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", **job.env}
        proc = await asyncio.create_subprocess_exec(
            *job.argv, cwd=ROOT, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=job.timeout)
            rc = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            out, err = await proc.communicate()
            rc = 124
            err += f"\n[qa_pool] timeout after {job.timeout}s".encode()
        return Result(job.name, rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"),
                      time.perf_counter() - start, job.meta)


async def _run_all(jobs_list, jobs, stop_when):
    sem = asyncio.Semaphore(jobs)
    cancelled = asyncio.Event()

    async def guarded(job):
        result = await _run_one(job, sem, cancelled)
        if stop_when is not None and not result.skipped and stop_when(result):
            cancelled.set()
        return result

    return await asyncio.gather(*(guarded(j) for j in jobs_list))


def run_many(jobs_list, jobs=None, stop_when=None):
    if not jobs_list:
        return []
    return asyncio.run(_run_all(list(jobs_list), jobs or default_jobs(), stop_when))


def python_job(name, script, *args, **kw):
    """Job для `python <script> args...` тем же интерпретатором."""
    return Job(name, [sys.executable, str(script), *map(str, args)], **kw)
