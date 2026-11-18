"""Launch only owned native children, with Linux parent-death protection."""
import os
import subprocess
from app_config import APP_ROOT


def spawn(command, **options):
    guard = APP_ROOT / 'backends/process-guard'
    if not guard.is_file():
        raise RuntimeError('Supervisor nativo ausente. Recompile o backend ou extraia novamente o pacote completo.')
    return subprocess.Popen([str(guard),str(os.getpid()),*map(str,command)], start_new_session=True, **options)
