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
                raise ValueError('Incorrect image format or dimensions.')
            image.verify()
        with Image.open(path) as image:
            image.load()
        if _signature(path) != signature:
            raise ValueError('The image changed during validation.')
        return ValidatedImage(Path(path).absolute(), tuple(dimensions), signature)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise RuntimeError(f'The backend did not produce a valid {dimensions[0]}×{dimensions[1]} PNG image.') from exc


def prepare_qwen_reference(source, destination, *, max_edge=512):
    """Prepare an isolated Qwen Image 2.1 input, preserving the uploaded original.

    Qwen3-VL requires multiples of 32; bound the image size for low-VRAM use.
    No crop: preserve the original aspect ratio and pad the edges with white.
    """
    from PIL import ImageOps
    with Image.open(source) as original:
        original.load()
        image = ImageOps.exif_transpose(original).convert('RGB')
    if max(image.size) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    width, height = image.size
    aligned = ((width + 31) // 32 * 32, (height + 31) // 32 * 32)
    if aligned != image.size:
        left = (aligned[0] - width) // 2
        top = (aligned[1] - height) // 2
        image = ImageOps.expand(image, (left, top, aligned[0] - width - left,
                                        aligned[1] - height - top), fill='white')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format='PNG')
    validate_image(destination, aligned)
    return destination


def crop_box(source_dimensions, dimensions, max_crop):
    width, height = dimensions
    src_width, src_height = source_dimensions
    if not width <= src_width <= width + max_crop or not height <= src_height <= height + max_crop:
        raise ValueError('The image dimensions are incompatible with the final crop.')
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
