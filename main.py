import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Team, Player, Tournament, Match

app = FastAPI(title="Football Tournament Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class IdResponse(BaseModel):
    id: str


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


@app.get("/")
def read_root():
    return {"message": "Football Tournament Manager Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:120]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"

    return response


# -----------------------------
# Teams
# -----------------------------
@app.post("/api/teams", response_model=IdResponse)
async def create_team(team: Team):
    new_id = create_document("team", team)
    return {"id": new_id}


@app.get("/api/teams")
async def list_teams():
    docs = get_documents("team")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -----------------------------
# Tournaments
# -----------------------------
@app.post("/api/tournaments", response_model=IdResponse)
async def create_tournament(tournament: Tournament):
    # Validate team ids exist (basic check)
    if tournament.team_ids:
        count = db["team"].count_documents({"_id": {"$in": [oid(t) for t in tournament.team_ids]}})
        if count != len(tournament.team_ids):
            raise HTTPException(status_code=400, detail="One or more team ids are invalid")
    new_id = create_document("tournament", tournament)
    return {"id": new_id}


@app.get("/api/tournaments")
async def list_tournaments():
    docs = get_documents("tournament")
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


# -----------------------------
# Match generation for round-robin
# -----------------------------
class GenerateScheduleRequest(BaseModel):
    tournament_id: str


def round_robin_pairings(team_ids: List[str]) -> List[tuple]:
    teams = team_ids.copy()
    if len(teams) % 2 == 1:
        teams.append("BYE")
    n = len(teams)
    rounds = n - 1
    half = n // 2
    schedule = []
    for r in range(rounds):
        pairings = []
        for i in range(half):
            a = teams[i]
            b = teams[n - 1 - i]
            if a != "BYE" and b != "BYE":
                pairings.append((a, b))
        schedule.append(pairings)
        # rotate
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return [match for round_ in schedule for match in round_]


@app.post("/api/tournaments/generate_schedule")
async def generate_schedule(payload: GenerateScheduleRequest):
    t = db["tournament"].find_one({"_id": oid(payload.tournament_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    team_ids = [str(x) for x in t.get("team_ids", [])]
    if len(team_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two teams required")

    created = []
    for home_id, away_id in round_robin_pairings(team_ids):
        match = Match(
            tournament_id=payload.tournament_id,
            home_team_id=home_id,
            away_team_id=away_id,
            status="scheduled",
        )
        new_id = create_document("match", match)
        created.append(new_id)
    return {"created_match_ids": created}


# -----------------------------
# Matches listing & results
# -----------------------------
class UpdateScoreRequest(BaseModel):
    match_id: str
    home_score: int
    away_score: int


@app.get("/api/tournaments/{tournament_id}/matches")
async def list_matches(tournament_id: str):
    docs = get_documents("match", {"tournament_id": tournament_id})
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/api/matches/update_score")
async def update_score(payload: UpdateScoreRequest):
    m = db["match"].find_one({"_id": oid(payload.match_id)})
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    db["match"].update_one(
        {"_id": oid(payload.match_id)},
        {"$set": {"status": "completed", "home_score": payload.home_score, "away_score": payload.away_score}},
    )
    return {"ok": True}


# -----------------------------
# Standings for round-robin
# -----------------------------
@app.get("/api/tournaments/{tournament_id}/standings")
async def standings(tournament_id: str):
    # Initialize table
    team_docs = list(db["team"].find({"_id": {"$in": [oid(t) for t in db["tournament"].find_one({"_id": oid(tournament_id)})["team_ids"]]}}))
    team_map = {str(t["_id"]): {"team_id": str(t["_id"]), "name": t.get("name"), "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0} for t in team_docs}

    matches = list(db["match"].find({"tournament_id": tournament_id, "status": "completed"}))
    for m in matches:
        h = team_map.get(m["home_team_id"])
        a = team_map.get(m["away_team_id"])
        if not h or not a:
            continue
        hs = int(m.get("home_score", 0))
        as_ = int(m.get("away_score", 0))
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hs
        h["ga"] += as_
        a["gf"] += as_
        a["ga"] += hs
        h["gd"] = h["gf"] - h["ga"]
        a["gd"] = a["gf"] - a["ga"]
        if hs > as_:
            h["won"] += 1
            a["lost"] += 1
            h["points"] += 3
        elif hs < as_:
            a["won"] += 1
            h["lost"] += 1
            a["points"] += 3
        else:
            h["drawn"] += 1
            a["drawn"] += 1
            h["points"] += 1
            a["points"] += 1

    table = list(team_map.values())
    table.sort(key=lambda x: (x["points"], x["gd"], x["gf"]), reverse=True)
    return table


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
