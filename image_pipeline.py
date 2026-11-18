"""Decode, validate and atomically finalize PNGs; never resample final pixels."""
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from PIL import Image


@dataclass(frozen=True)
class ValidatedImage:
    """Reuse a full PNG check only while the same file remains unchanged."""
    path: Path
    dimensions: tuple
    signature: tuple


def _signature(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def validate_image(path, dimensions):
    try:
        signature = _signature(path)
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != tuple(dimensions):
                raise ValueError('Formato ou dimensões incorretos.')
            image.verify()
        with Image.open(path) as image:
            image.load()
        if _signature(path) != signature:
            raise ValueError('A imagem mudou durante a validação.')
        return ValidatedImage(Path(path).absolute(), tuple(dimensions), signature)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise RuntimeError(f'O backend não produziu uma imagem PNG válida em {dimensions[0]}×{dimensions[1]}.') from exc


def finalize(source, destination, source_dimensions, dimensions, check, *, validation=None, max_crop=64):
    check()
    if not (isinstance(validation, ValidatedImage)
            and validation.path == Path(source).absolute()
            and validation.dimensions == tuple(source_dimensions)
            and validation.signature == _signature(source)):
        validate_image(source, source_dimensions)
    width, height = dimensions
    if not width <= source_dimensions[0] <= width+max_crop or not height <= source_dimensions[1] <= height+max_crop:
        raise ValueError('Dimensões incompatíveis com o recorte final.')
    destination = Path(destination)
    if tuple(source_dimensions) == tuple(dimensions):
        # Job artifacts share a filesystem; publish the original PNG atomically.
        check()
        os.replace(source, destination)
        return
    fd, temporary = tempfile.mkstemp(prefix='.'+destination.stem, suffix='.png', dir=destination.parent)
    os.close(fd)
    try:
        check()
        with Image.open(source) as image:
            left,top = (image.width-width)//2,(image.height-height)//2
            image.crop((left,top,left+width,top+height)).save(temporary,format='PNG')
        validate_image(temporary,dimensions)
        check()
        os.replace(temporary,destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
