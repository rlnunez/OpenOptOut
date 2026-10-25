"""
Data Rights Protocol (DRP) implementation for OpenOptOut.
"""

from .schema import (
    DrpIdentity,
    DrpExerciseRequest,
    DrpExerciseResponse,
    DrpStatusResponse,
    REGIMES,
    VALID_RIGHTS,
    STATUSES,
    DRP_VERSION,
)
from .client import DrpClient, DrpError

__all__ = [
    "DrpIdentity",
    "DrpExerciseRequest",
    "DrpExerciseResponse",
    "DrpStatusResponse",
    "DrpClient",
    "DrpError",
    "REGIMES",
    "VALID_RIGHTS",
    "STATUSES",
    "DRP_VERSION",
]

