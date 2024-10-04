from dataclasses import dataclass
from typing import Optional


@dataclass
class ProjectCacheConfig:
    """Project cache configuration"""

    enable: bool = True
    refresh_days_period: Optional[int] = None


@dataclass
class Project:
    """All information for project"""

    name: str
    location: str
    file: str
    type_storage: str
    valid: bool = True
    cache_config: ProjectCacheConfig = ProjectCacheConfig()
