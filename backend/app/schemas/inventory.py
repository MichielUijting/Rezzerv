from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class SpaceCreate(BaseModel):
    naam: str
    household_id: Optional[str] = None
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Ruimtenaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Ruimtenaam mag maximaal 120 tekens bevatten")
        return normalized


class SpaceUpdateRequest(BaseModel):
    naam: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Ruimtenaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Ruimtenaam mag maximaal 120 tekens bevatten")
        return normalized


class SublocationCreate(BaseModel):
    naam: str
    space_id: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Sublocatienaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Sublocatienaam mag maximaal 120 tekens bevatten")
        return normalized


class SublocationUpdateRequest(BaseModel):
    naam: str
    space_id: str
    active: bool = True

    @field_validator("naam")
    @classmethod
    def validate_naam(cls, value):
        normalized = ' '.join(str(value or '').strip().split())
        if not normalized:
            raise ValueError("Sublocatienaam is verplicht")
        if len(normalized) > 120:
            raise ValueError("Sublocatienaam mag maximaal 120 tekens bevatten")
        return normalized


class InventoryCreate(BaseModel):
    naam: str
    aantal: int
    space_id: str
    sublocation_id: Optional[str] = None


class InventoryUpdate(BaseModel):
    naam: str
    aantal: int
    space_id: Optional[str] = None
    sublocation_id: Optional[str] = None
    space_name: Optional[str] = None
    sublocation_name: Optional[str] = None
