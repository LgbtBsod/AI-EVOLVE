from __future__ import annotations

from dataclasses import dataclass

from .social_types import InteractionType, RelationshipType


@dataclass
class SocialRelation:
    source_id: str
    target_id: str
    relationship: RelationshipType = RelationshipType.NEUTRAL
    last_interaction: InteractionType = InteractionType.TALK
