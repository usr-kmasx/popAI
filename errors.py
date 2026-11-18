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
    where=f' Consulte logs/{log.name}.'
    if any(s in text for s in ('errordevicelost','device lost','vk_error_device_lost')):
        return EngineFailure('device_lost',f'A GPU perdeu o contexto Vulkan durante {stage}. Aguarde o driver se recuperar antes de tentar novamente.'+where)
    if any(s in text for s in ('outofdevicememory','out_of_device_memory','out of device memory','failed to allocate vulkan','not enough vram','insufficient vram')):
        return EngineFailure('vram_exhausted','Faltou memória na GPU. Use geração Leve; se a falha for no VAE, reduza o bloco do VAE. Feche outros programas que usam a GPU.'+where)
    if any(s in text for s in ('outofhostmemory','out_of_host_memory','out of host memory','bad_alloc','cannot allocate memory')):
        return EngineFailure('ram_exhausted','Faltou memória RAM. Ative mmap e feche outros programas antes de tentar novamente.'+where)
    if any(s in text for s in ('invalid magic','unexpected end of file','truncated','invalid tensor','failed to load model','failed to load diffusion')):
        return EngineFailure('invalid_component','O motor não conseguiu ler um componente. Confira se os arquivos oficiais estão completos e o SSD está disponível.'+where)
    if returncode in (-9,137):
        return EngineFailure('process_killed','O sistema encerrou o motor. Verifique os registros do sistema e o uso de memória antes de tentar novamente.'+where)
    code=f' (código {returncode})' if returncode is not None else ''
    return EngineFailure('engine_failed',f'O motor falhou durante {stage}{code}.'+where)


def explain(exc):
    if isinstance(exc,EngineFailure):
        return exc
    if isinstance(exc,OSError) and exc.errno==errno.ENOSPC:
        return EngineFailure('disk_full','Acabou o espaço na pasta do projeto. Libere espaço e conclua novamente a imagem, se houver uma base válida.','storage')
    if isinstance(exc,MemoryError):
        return EngineFailure('ram_exhausted','Faltou memória RAM. Feche outros programas e mantenha mmap ativado.')
    return EngineFailure('generation_failed',str(exc))
