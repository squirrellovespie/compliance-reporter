from __future__ import annotations
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class Section(BaseModel):
    id: str = Field(..., description="Stable unique id per framework (e.g., 'exec_summary')")
    name: str
    position: int = Field(..., ge=1, description="1-based order in the report")
    prompt: str = Field("", description="LLM prompt for this section")

class SectionUpsertRequest(BaseModel):
    framework: str
    sections: List[Section]

    @validator("sections")
    def validate_unique_ids_positions(cls, v):
        ids = [s.id for s in v]
        if len(set(ids)) != len(ids):
            raise ValueError("section ids must be unique per framework")
        positions = [s.position for s in v]
        if len(set(positions)) != len(positions):
            raise ValueError("positions must be unique per framework")
        return v

class SectionListResponse(BaseModel):
    framework: str
    sections: List[Section]

class RunReportRequest(BaseModel):
    framework: str
    firm: str
    scope: Optional[str] = None
    selected_section_ids: List[str] = Field(default_factory=list)
    prompt_overrides: Dict[str, str] = Field(default_factory=dict)  # {section_id: prompt}
