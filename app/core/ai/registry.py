"""
AIFeatureRegistry — central registry for AI feature definitions.

New features are added by calling AIFeatureRegistry.register() at module
import time.  The context menu and future AI modules both read from this
registry, so adding a feature here automatically surfaces it in the UI.

Usage by AI modules:
    from app.core.ai.registry import AIFeatureRegistry
    for feature in AIFeatureRegistry.all():
        if feature.key in camera.enabled_features:
            # activate this feature's inference pipeline
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Optional


@dataclass(frozen=True)
class AIFeature:
    """Immutable descriptor for a single AI feature."""

    key: str
    name: str
    description: str = ""
    category: str = ""
    available: bool = True


class AIFeatureRegistry:
    """Class-level registry — no instantiation required.

    All methods are classmethods so the registry acts as a global
    singleton without needing a module-level instance.
    """

    _features: ClassVar[list[AIFeature]] = []

    @classmethod
    def register(cls, feature: AIFeature) -> None:
        """Register a new feature.  Duplicates by key are silently ignored."""
        if not any(f.key == feature.key for f in cls._features):
            cls._features.append(feature)

    @classmethod
    def all(cls) -> list[AIFeature]:
        """Return all registered features in registration order."""
        return list(cls._features)

    @classmethod
    def by_category(cls) -> dict[str, list[AIFeature]]:
        """Return features grouped by category, preserving registration order."""
        grouped: dict[str, list[AIFeature]] = {}
        for f in cls._features:
            cat = f.category or "Other"
            grouped.setdefault(cat, []).append(f)
        return grouped

    @classmethod
    def get(cls, key: str) -> Optional[AIFeature]:
        """Return a feature by key, or None."""
        for f in cls._features:
            if f.key == key:
                return f
        return None

    @classmethod
    def keys(cls) -> list[str]:
        """Return all registered feature keys."""
        return [f.key for f in cls._features]


# ── Built-in features ────────────────────────────────────────────────────────
# Registered at import time.  Future modules can call register() to add more.

_R = AIFeatureRegistry  # alias for brevity

# ── Analytics ────────────────────────────────────────────────────────────────
_R.register(AIFeature(
    key="fall_detection",
    name="Fall Detection",
    description="Detects falls and sudden collapses",
    category="Analytics",
    available=True,
))
_R.register(AIFeature(
    key="restricted_area",
    name="Restricted Area",
    description="Detects unauthorized entry into restricted zones",
    category="Analytics",
    available=True,
))
_R.register(AIFeature(
    key="intrusion_detection",
    name="Intrusion Detection",
    description="Detects intrusion into monitored areas",
    category="Analytics",
    available=False,
))
_R.register(AIFeature(
    key="loitering_detection",
    name="Loitering Detection",
    description="Detects prolonged presence in designated areas",
    category="Analytics",
    available=False,
))
_R.register(AIFeature(
    key="person_counting",
    name="Person Counting",
    description="Counts people entering or leaving an area",
    category="Analytics",
    available=False,
))
_R.register(AIFeature(
    key="crowd_density",
    name="Crowd Density",
    description="Measures crowd density and alerts on overcrowding",
    category="Analytics",
    available=False,
))

# ── Face ─────────────────────────────────────────────────────────────────────
_R.register(AIFeature(
    key="face_detection",
    name="Face Detection",
    description="Detects faces in the camera frame",
    category="Face",
    available=False,
))
_R.register(AIFeature(
    key="face_recognition",
    name="Face Recognition",
    description="Identifies known individuals by facial features",
    category="Face",
    available=False,
))

# ── Vehicle ──────────────────────────────────────────────────────────────────
_R.register(AIFeature(
    key="vehicle_detection",
    name="Vehicle Detection",
    description="Detects and classifies vehicles in the camera frame",
    category="Vehicle",
    available=False,
))
_R.register(AIFeature(
    key="license_plate_recognition",
    name="License Plate Recognition",
    description="Reads and identifies vehicle license plates",
    category="Vehicle",
    available=False,
))
_R.register(AIFeature(
    key="illegal_parking",
    name="Illegal Parking",
    description="Detects vehicles parked in restricted areas",
    category="Vehicle",
    available=False,
))
_R.register(AIFeature(
    key="wrong_way",
    name="Wrong Way",
    description="Detects vehicles traveling in the wrong direction",
    category="Vehicle",
    available=False,
))
_R.register(AIFeature(
    key="speed_detection",
    name="Speed Detection",
    description="Estimates vehicle speed from camera footage",
    category="Vehicle",
    available=False,
))

# ── Safety ───────────────────────────────────────────────────────────────────
_R.register(AIFeature(
    key="smoke_detection",
    name="Smoke Detection",
    description="Detects smoke in the camera frame",
    category="Safety",
    available=True,
))
_R.register(AIFeature(
    key="fire_detection",
    name="Fire Detection",
    description="Detects fire and flame in the camera frame",
    category="Safety",
    available=True,
))
_R.register(AIFeature(
    key="ppe_detection",
    name="PPE Detection",
    description="Detects presence or absence of personal protective equipment",
    category="Safety",
    available=True,
))

# ── Object ───────────────────────────────────────────────────────────────────
_R.register(AIFeature(
    key="abandoned_object",
    name="Abandoned Object",
    description="Detects objects left behind in monitored areas",
    category="Object",
    available=False,
))
_R.register(AIFeature(
    key="object_removal",
    name="Object Removal",
    description="Detects when objects are removed from monitored areas",
    category="Object",
    available=False,
))
