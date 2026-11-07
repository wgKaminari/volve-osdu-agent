"""Core data types shared by every pipeline step (PROJECT_GUIDE.md section 6.3).

A Fact is one value about a wellbore with the evidence for it. A ReviewFlag is something a human
must look at. An Issue is a validation finding about an emitted record.
"""

from typing import Literal

from pydantic import BaseModel, Field

Method = Literal["parsed", "llm_extracted", "derived"]
Severity = Literal["info", "warn", "block"]


class Provenance(BaseModel):
    """Where a value came from. `locator` points inside the file, e.g. "LAS:~Well/ELEV"."""

    source_file: str
    locator: str
    method: Method
    quote: str | None = None  # required for llm_extracted, checked by the grounding rule
    model: str | None = None
    prompt_version: str | None = None


class Fact(BaseModel):
    """One value about a wellbore, e.g. name="kb_elevation_m", value=54.9, unit="m"."""

    name: str
    value: float | str | None
    unit: str | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    confidence: float | None = None


class ReviewFlag(BaseModel):
    """Something a human must decide. `candidates` hold every competing value with its source."""

    severity: Severity
    fact: str
    reason: str  # "conflict", "log_below_survey", "plan_not_actual", "unit_converted", ...
    message: str
    candidates: list[Fact] = Field(default_factory=list)


class Issue(BaseModel):
    """A validation finding. Any "error" means the record set is not ready to ingest."""

    rule: int
    severity: Literal["error", "warn", "info"]
    record_id: str | None
    path: str | None = None
    message: str
