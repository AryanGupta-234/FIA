from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    budget_max: float | None = Field(default=None, gt=0, le=10_000_000)
    category: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=20, ge=1, le=50)
    fetch_product_pages: bool = True


class PreferenceUpdate(BaseModel):
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    preferred_colours: list[str] = Field(default_factory=list)
    sizes: dict[str, str] = Field(default_factory=dict)
    style_notes: str = Field(default="", max_length=2000)
    budget_default: float | None = Field(default=None, gt=0, le=10_000_000)
    price_alert_threshold_percent: float = Field(default=2.0, ge=0, le=100)


class SavedSearchCreate(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    budget_max: float | None = Field(default=None, gt=0, le=10_000_000)
    category: str | None = Field(default=None, max_length=80)


class SavedSearchUpdate(BaseModel):
    active: bool
