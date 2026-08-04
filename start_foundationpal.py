'''Start the FoundationPal API and web development servers together.'''

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent
API_DIR = PROJECT_ROOT / 'api'
WEB_DIR = PROJECT_ROOT / 'web'
USER_DATABASE = API_DIR / 'data' / 'foundationpal_user.sqlite3'
PREFERRED_PYTHON = Path(r'F:\Anaconda\envs\fundagent\python.exe')


def require_startup_files() -> None:
    django_entry = API_DIR / 'manage.py'
    frontend_dependencies = WEB_DIR / 'node_modules'
    if not django_entry.is_file():
        raise RuntimeError(f'Missing Django entry: {django_entry}')
    if not frontend_dependencies.is_dir():
        raise RuntimeError(f'Missing frontend dependencies: {frontend_dependencies}')
    if not USER_DATABASE.is_file():
        raise RuntimeError(f'Missing user database: {USER_DATABASE}')
    if shutil.which('npm.cmd') is None:
        raise RuntimeError('npm.cmd was not found on PATH.')


def api_command() -> list[str]:
    python = PREFERRED_PYTHON if PREFERRED_PYTHON.is_file() else Path(sys.executable)
    return [str(python), 'manage.py', 'runserver', '127.0.0.1:8000']


def api_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment['DATABASE_URL'] = f'sqlite:///{USER_DATABASE.as_posix()}'
    return environment


def web_command() -> list[str]:
    command_shell = os.environ.get('COMSPEC', 'cmd.exe')
    return [command_shell, '/c', 'call npm.cmd run dev']


def stop_process(process: Optional[subprocess.Popen]) -> None:
    if process is None or process.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(
            ['taskkill', '/pid', str(process.pid), '/t', '/f'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()


def main() -> int:
    require_startup_files()
    api_process: Optional[subprocess.Popen] = None
    web_process: Optional[subprocess.Popen] = None
    try:
        api_process = subprocess.Popen(api_command(), cwd=API_DIR, env=api_environment())
        web_process = subprocess.Popen(web_command(), cwd=WEB_DIR)
        print('FoundationPal is starting.')
        print('API: http://127.0.0.1:8000')
        print('Web: http://127.0.0.1:5173/app/login')
        print('Press Ctrl+C to stop both servers.')
        while api_process.poll() is None and web_process.poll() is None:
            time.sleep(0.25)
        return 1
    except KeyboardInterrupt:
        print('\nStopping FoundationPal.')
        return 0
    finally:
        stop_process(web_process)
        stop_process(api_process)


if __name__ == '__main__':
    raise SystemExit(main())
