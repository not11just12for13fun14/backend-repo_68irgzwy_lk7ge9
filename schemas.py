"""
Database Schemas for Football Tournament Manager

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercase of the class name (handled by the Flames platform conventions).

Collections:
- team
- player
- tournament
- match
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import date

# -----------------------------
# Core Domain Schemas
# -----------------------------

class Team(BaseModel):
    name: str = Field(..., description="Team name")
    city: Optional[str] = Field(None, description="City or region")
    logo_url: Optional[str] = Field(None, description="Public logo URL")


class Player(BaseModel):
    name: str = Field(..., description="Player full name")
    position: Optional[str] = Field(None, description="Playing position")
    number: Optional[int] = Field(None, ge=0, le=99, description="Jersey number")
    team_id: Optional[str] = Field(None, description="Associated team id (stringified ObjectId)")


class Tournament(BaseModel):
    name: str = Field(..., description="Tournament name")
    start_date: Optional[date] = Field(None, description="Planned start date")
    format: Literal["round_robin"] = Field("round_robin", description="Tournament format")
    team_ids: List[str] = Field(default_factory=list, description="Participating team ids")


class Match(BaseModel):
    tournament_id: str = Field(..., description="Tournament id")
    home_team_id: str = Field(..., description="Home team id")
    away_team_id: str = Field(..., description="Away team id")
    scheduled_date: Optional[date] = Field(None, description="Scheduled date")
    status: Literal["scheduled", "completed"] = Field("scheduled", description="Match status")
    home_score: Optional[int] = Field(None, ge=0, description="Home team score (when completed)")
    away_score: Optional[int] = Field(None, ge=0, description="Away team score (when completed)")

# Note: The Flames database viewer can introspect these at /schema.
