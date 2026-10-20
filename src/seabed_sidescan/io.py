"""Shared file validation and replacement for processing outputs."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path


def validate_paths(inputs: Iterable[Path], outputs: Iterable[Path]) -> None:
    """Reject input/output aliases, hard links and colliding destinations."""
    sources = [Path(path).expanduser().resolve() for path in inputs]
    for source in tuple(sources):
        if source.suffix.lower() == ".shp":
            sources.extend(source.with_suffix(suffix) for suffix in (".prj", ".dbf", ".shx", ".cpg", ".qix"))
    targets = [Path(path).expanduser().resolve() for path in outputs]
    for index, target in enumerate(targets):
        if target.exists() and not target.is_file():
            raise ValueError(f"Output path is not a file: {target}")
        for other in targets[:index]:
            if target == other or (target.exists() and other.exists() and os.path.samefile(target, other)):
                raise ValueError("Output paths must be distinct.")
        for source in sources:
            if target == source or (target.exists() and source.is_file() and os.path.samefile(target, source)):
                raise ValueError(f"Output path must differ from input paths: {target}")


@contextmanager
def atomic_output(path: Path) -> Iterator[Path]:
    """Replace one file only after its staged writer closes successfully.

    GeoTIFF sidecars belonging to a previous output are removed on commit so
    an old mask or overview cannot override the new raster. This is a per-file
    transaction; a process crash while committing several products is not a
    transaction across all of those products.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    os.close(descriptor)
    staged = Path(temporary)
    sidecars = (".msk", ".aux.xml", ".ovr") if path.suffix.lower() in {".tif", ".tiff"} else ()
    try:
        yield staged
        os.replace(staged, path)
        for suffix in sidecars:
            new = Path(str(staged) + suffix)
            old = Path(str(path) + suffix)
            if new.exists():
                os.replace(new, old)
            elif old.exists():
                old.unlink()
    finally:
        for temporary_path in [staged, *(Path(str(staged) + suffix) for suffix in sidecars)]:
            temporary_path.unlink(missing_ok=True)


def windows(width: int, height: int, bands: int = 1, rows_limit: int = 256):
    """Iterate bounded pixel windows independently of the source TIFF tiling."""
    from rasterio.windows import Window

    columns = min(width, 512)
    rows = max(1, min(rows_limit, 131072 // max(1, columns * bands)))
    for row in range(0, height, rows):
        for column in range(0, width, columns):
            yield Window(column, row, min(columns, width - column), min(rows, height - row))
