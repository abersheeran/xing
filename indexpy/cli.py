import os
import signal
import subprocess
import sys
import time
from multiprocessing import cpu_count
from typing import List, Union

import click

from .__version__ import __version__
from .conf import serve_config
from .utils import import_module


def execute(command: Union[List[str], str]) -> int:
    if isinstance(command, str):
        command = [command]

    click.echo("Execute command: ", nl=False)
    click.secho(" ".join(command), fg="green")

    process = subprocess.Popen(" ".join(command), shell=True)

    def sigterm_handler(signo, frame):
        process.terminate()
        process.wait()

    signal.signal(signal.SIGINT, sigterm_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)

    while process.poll() is None:
        time.sleep(1)

    return process.returncode


@click.group(help=f"Index.py {__version__}")
def index_cli():
    pass


@index_cli.command(help="use uvicorn to run Index.py application")
@click.argument("application", default=lambda: serve_config.APP)
def serve(application):
    import uvicorn

    sys.path.insert(0, os.getcwd())

    uvicorn.run(
        application,
        host=serve_config.HOST,
        port=serve_config.PORT,
        log_level=serve_config.LOG_LEVEL,
        interface="asgi3",
        lifespan="on",
        reload=serve_config.AUTORELOAD,
    )


try:
    from gunicorn.app.wsgiapp import run as run_gunicorn_process_by_sys_argv
except ImportError:
    pass
else:
    MASTER_PID_FILE = ".gunicorn.pid"

    def read_gunicorn_master_pid(pid_file: str = MASTER_PID_FILE) -> int:
        try:
            with open(os.path.join(os.getcwd(), MASTER_PID_FILE)) as file:
                return int(file.read())
        except FileNotFoundError:
            sys.exit(
                (
                    f'File "{MASTER_PID_FILE}" not found, '
                    + "please make sure you have started gunicorn using the "
                    + "`index-cli gunicorn start --daemon ...`."
                )
            )

    @click.group(help="use gunicorn to run Index.py application")
    def gunicorn_cli():
        pass

    @gunicorn_cli.command(help="Run gunicorn")
    @click.option("--workers", "-w", default=cpu_count())
    @click.option("--worker-class", "-k", default="uvicorn.workers.UvicornWorker")
    @click.option("--daemon", "-d", default=False, is_flag=True)
    @click.option(
        "--configuration",
        "-c",
        type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    )
    @click.argument("application", default=lambda: serve_config.APP)
    def start(workers, worker_class, daemon, configuration, application):
        command = (
            "gunicorn"
            + f" -k {worker_class}"
            + f" --bind {serve_config.HOST}:{serve_config.PORT}"
            + f" --chdir {os.getcwd()}"
            + f" --workers {workers}"
            + f" --pid {MASTER_PID_FILE}"
            + f" --log-level {serve_config.LOG_LEVEL}"
        )
        args = command.split(" ")
        if daemon:
            args.extend("-D --log-file log.index".split(" "))
        if serve_config.AUTORELOAD:
            args.append("--reload")
        if configuration:
            args.append("-c")
            args.append(configuration.strip())
        args.append(application)

        sys.argv = args
        run_gunicorn_process_by_sys_argv()

    # Gunicorn signal handler
    # https://docs.gunicorn.org/en/stable/signals.html

    @gunicorn_cli.command(help="Increment the number of processes by one")
    def incr():
        os.kill(read_gunicorn_master_pid(), signal.SIGTTIN)

    @gunicorn_cli.command(help="Decrement the number of processes by one")
    def decr():
        os.kill(read_gunicorn_master_pid(), signal.SIGTTOU)

    @gunicorn_cli.command(help="Stop gunicorn processes")
    @click.option("--force", "-f", default=False, is_flag=True)
    def stop(force):
        os.kill(read_gunicorn_master_pid(), signal.SIGINT if force else signal.SIGTERM)

    @gunicorn_cli.command(help="Reload gunicorn processes")
    @click.option("--gracefully", default=False, is_flag=True)
    def reload(gracefully):
        oldpid = read_gunicorn_master_pid()

        if not gracefully:
            return os.kill(oldpid, signal.SIGHUP)

        os.kill(oldpid, signal.SIGUSR2)
        os.kill(oldpid, signal.SIGWINCH)

    index_cli.add_command(gunicorn_cli, "gunicorn")

import_module("commands")
