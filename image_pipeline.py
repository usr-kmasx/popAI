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


def crop_box(source_dimensions, dimensions, max_crop):
    width, height = dimensions
    src_width, src_height = source_dimensions
    if not width <= src_width <= width + max_crop or not height <= src_height <= height + max_crop:
        raise ValueError('Dimensões incompatíveis com o recorte final.')
    left, top = (src_width - width) // 2, (src_height - height) // 2
    return left, top, left + width, top + height


def finalize(source, destination, source_dimensions, dimensions, check, *, validation=None, max_crop=64, publish=os.replace):
    check()
    if not (isinstance(validation, ValidatedImage)
            and validation.path == Path(source).absolute()
            and validation.dimensions == tuple(source_dimensions)
            and validation.signature == _signature(source)):
        validate_image(source, source_dimensions)
    box = crop_box(source_dimensions, dimensions, max_crop)
    destination = Path(destination)
    if tuple(source_dimensions) == tuple(dimensions):
        # Job artifacts share a filesystem; publish the original PNG atomically.
        check()
        publish(source, destination)
        return
    fd, temporary = tempfile.mkstemp(prefix='.'+destination.stem, suffix='.png', dir=destination.parent)
    os.close(fd)
    try:
        check()
        with Image.open(source) as image:
            image.crop(box).save(temporary,format='PNG')
        validate_image(temporary,dimensions)
        check()
        publish(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
