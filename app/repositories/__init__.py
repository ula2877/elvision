"""
Abstract repository interfaces for data access.
Clean Architecture's Repository Pattern — domain layer defines contracts,
infrastructure layer provides implementations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from app.models import CameraInfo, CameraGroup


class CameraRepository(ABC):
    """Contract for camera data access."""

    @abstractmethod
    def list_all(self) -> Sequence[CameraInfo]:
        ...

    @abstractmethod
    def get_by_id(self, camera_id: str) -> Optional[CameraInfo]:
        ...

    @abstractmethod
    def add(self, camera: CameraInfo) -> None:
        ...

    @abstractmethod
    def update(self, camera: CameraInfo) -> None:
        ...

    @abstractmethod
    def remove(self, camera_id: str) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...


class GroupRepository(ABC):
    """Contract for group data access."""

    @abstractmethod
    def list_all(self) -> Sequence[CameraGroup]:
        ...

    @abstractmethod
    def get_by_id(self, group_id: str) -> Optional[CameraGroup]:
        ...

    @abstractmethod
    def add(self, group: CameraGroup) -> None:
        ...

    @abstractmethod
    def update(self, group: CameraGroup) -> None:
        ...

    @abstractmethod
    def remove(self, group_id: str) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...
