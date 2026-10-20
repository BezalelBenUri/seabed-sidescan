"""Side-scan sonar raster analysis without a QGIS runtime dependency."""

from .api import (
    ClassificationResult,
    CleanupResult,
    EvaluationResult,
    FeatureStackResult,
    MosaicResult,
    RawProcessingResult,
    TextureResult,
    build_mosaics,
    clean_classification,
    clip_raster,
    create_mask,
    evaluate_clusters,
    extract_textures,
    process_sonar,
    stack_features,
)
from .api import classify as classify_facies

__version__ = "0.1.0"

__all__ = [
    "__version__", "build_mosaics", "classify_facies", "clean_classification",
    "clip_raster", "create_mask", "evaluate_clusters", "extract_textures",
    "process_sonar", "stack_features", "ClassificationResult", "CleanupResult",
    "EvaluationResult", "FeatureStackResult", "MosaicResult", "RawProcessingResult", "TextureResult",
]
