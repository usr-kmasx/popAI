"""Translate native failures into specific, actionable local errors."""
import errno
import os
from pathlib import Path


class EngineFailure(RuntimeError):
    def __init__(self, code, message, action='settings'):
        super().__init__(message)
        self.code, self.action = code, action


def native_failure(log, stage, returncode=None, detail='', offset=0):
    log=Path(log)
    try:
        with log.open('rb') as stream:
            stream.seek(-min(max(0,log.stat().st_size-offset),16384),os.SEEK_END)
            detail += '\n'+stream.read().decode('utf-8',errors='replace')
    except OSError:
        pass
    text=detail.lower()
    where=f' Session log: {log}.'
    if any(s in text for s in ('errordevicelost','device lost','vk_error_device_lost')):
        return EngineFailure('device_lost',f'The GPU lost its Vulkan context during {stage}. Wait for the driver to recover before trying again.'+where)
    if any(s in text for s in ('outofdevicememory','out_of_device_memory','out of device memory','failed to allocate vulkan','not enough vram','insufficient vram')):
        return EngineFailure('vram_exhausted','The GPU ran out of memory. Set the generation size to Light and close other apps that use the GPU. If the VAE failed, reduce the VAE tile size.'+where)
    if any(s in text for s in ('outofhostmemory','out_of_host_memory','out of host memory','bad_alloc','cannot allocate memory')):
        return EngineFailure('ram_exhausted','The system ran out of RAM. Enable mmap and close other apps before trying again.'+where)
    if any(s in text for s in ('invalid magic','unexpected end of file','truncated','invalid tensor','failed to load model','failed to load diffusion')):
        return EngineFailure('invalid_component','The engine could not read a component. Check that the official files are complete and the SSD is available.'+where)
    if returncode in (-9,137):
        return EngineFailure('process_killed','The system stopped the engine. Check the system logs and memory usage before trying again.'+where)
    code=f' (exit code {returncode})' if returncode is not None else ''
    return EngineFailure('engine_failed',f'The engine failed during {stage}{code}.'+where)


def explain(exc):
    if isinstance(exc,EngineFailure):
        return exc
    if isinstance(exc,OSError) and exc.errno==errno.ENOSPC:
        return EngineFailure('disk_full','The project folder ran out of space. Free up space, then retry finishing the image if a valid base image is available.','storage')
    if isinstance(exc,MemoryError):
        return EngineFailure('ram_exhausted','The system ran out of RAM. Close other apps and keep mmap enabled.')
    return EngineFailure('generation_failed',str(exc))
