from enum import StrEnum


class ProductionBatchStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProductionStage(StrEnum):
    PRESSING = "pressing"
    FILTERING = "filtering"
    FILLING = "filling"
    QUALITY_CHECK = "quality_check"
    PACKAGING = "packaging"
