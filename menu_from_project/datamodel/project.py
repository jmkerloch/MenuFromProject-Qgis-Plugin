from dataclasses import dataclass
from typing import Optional


@dataclass
class Project:
    name: str
    location: str
    file: str
    type_storage: str
    valid: bool = True
