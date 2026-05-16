"""Project pipelines."""
from __future__ import annotations

from kedro.pipeline import Pipeline

from campus_ml.pipelines.pipelines import (
    create_canteen_pipeline,
    create_library_pipeline,
    create_energy_pipeline,
)


def register_pipelines() -> dict[str, Pipeline]:
    """Register the project's pipelines."""
    canteen = create_canteen_pipeline()
    library = create_library_pipeline()
    energy  = create_energy_pipeline()

    return {
        "canteen_congestion": canteen,
        "library_congestion": library,
        "energy_forecast":    energy,
        "__default__":        canteen + library + energy,
    }
