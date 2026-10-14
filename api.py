"""REST API for Smart Sales. Run: uvicorn api:app --port 8000   Docs: http://localhost:8000/docs"""
import secrets
import time
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import auth
from core.seed import setup
from services import customers, followups, leads, opportunities, reports

app = FastAPI(title="Smart Sales API", description="Login with POST /api/auth/login, then send header: Authorization: Bearer <token>")
setup()

TOKENS = {}          # token -> user dict (kept in memory, cleared on restart)
LOGIN_HITS = {}      # ip -> list of request times, for rate limit


# ---------- request bodies ----------

class LoginIn(BaseModel):
    email: str
    password: str


class CustomerIn(BaseModel):
    name: str
    email: str
    phone: str
    company: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    status: str = "Active"
    notes: Optional[str] = None
    assigned_to: Optional[int] = None


class LeadIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    source: str = "Website"
    status: str = "New"
    priority: str = "Medium"
    expected_value: float = 0
    notes: Optional[str] = None
    assigned_to: Optional[int] = None


class OpportunityIn(BaseModel):
    name: str
    customer_id: int
    amount: float
    probability: int
    stage: str = "Qualification"
    close_date: date
    source: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[int] = None


class FollowUpIn(BaseModel):
    customer_id: Optional[int] = None
    lead_id: Optional[int] = None
    fu_date: date
    fu_type: str = "Call"
    subject: str
    remarks: Optional[str] = None
    assigned_to: Optional[int] = None


# ---------- helpers ----------

def current_user(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "")
    user = TOKENS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


def bad_request(errors):
    raise HTTPException(status_code=400, detail={"message": "Validation failed.", "errors": errors})


@app.exception_handler(PermissionError)
def no_permission(request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


# ---------- auth ----------

@app.post("/api/auth/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    hits = [t for t in LOGIN_HITS.get(ip, []) if time.time() - t < 60]
    if len(hits) >= 5:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try after a minute.")
    LOGIN_HITS[ip] = hits + [time.time()]

    user, error = auth.login(body.email, body.password)
    if error:
        raise HTTPException(status_code=401, detail=error)
    token = secrets.token_hex(24)
    TOKENS[token] = user
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default=""), user=Depends(current_user)):
    auth.logout(user)
    TOKENS.pop(authorization.replace("Bearer ", ""), None)
    return {"message": "Logged out."}


# ---------- customers ----------

@app.get("/api/customers")
def get_customers(q: str = "", user=Depends(current_user)):
    return customers.list_customers(user, q)


@app.get("/api/customers/{cid}")
def get_customer(cid: int, user=Depends(current_user)):
    row = customers.get_customer(user, cid)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return row


@app.post("/api/customers", status_code=201)
def create_customer(body: CustomerIn, user=Depends(current_user)):
    cid, errors = customers.create_customer(user, body.model_dump())
    if errors:
        if any("already exists" in m for m in errors.values()):
            raise HTTPException(status_code=409, detail={"message": "Customer already exists.", "errors": errors})
        bad_request(errors)
    return customers.get_customer(user, cid)


@app.put("/api/customers/{cid}")
def update_customer(cid: int, body: CustomerIn, user=Depends(current_user)):
    if not customers.get_customer(user, cid):
        raise HTTPException(status_code=404, detail="Customer not found.")
    errors = customers.update_customer(user, cid, body.model_dump())
    if errors:
        if any("already exists" in m for m in errors.values()):
            raise HTTPException(status_code=409, detail={"message": "Customer already exists.", "errors": errors})
        bad_request(errors)
    return customers.get_customer(user, cid)


@app.delete("/api/customers/{cid}", status_code=204)
def delete_customer(cid: int, user=Depends(current_user)):
    message = customers.delete_customer(user, cid)
    if message == "Customer not found.":
        raise HTTPException(status_code=404, detail=message)


# ---------- leads ----------

@app.get("/api/leads")
def get_leads(q: str = "", status: str = "", user=Depends(current_user)):
    return leads.list_leads(user, q, status)


@app.get("/api/leads/{lid}")
def get_lead(lid: int, user=Depends(current_user)):
    row = leads.get_lead(user, lid)
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return row


@app.post("/api/leads", status_code=201)
def create_lead(body: LeadIn, user=Depends(current_user)):
    lid, errors = leads.create_lead(user, body.model_dump())
    if errors:
        bad_request(errors)
    return leads.get_lead(user, lid)


# ---------- opportunities ----------

@app.get("/api/opportunities")
def get_opportunities(q: str = "", stage: str = "", user=Depends(current_user)):
    return opportunities.list_opps(user, q, stage)


@app.get("/api/opportunities/{oid}")
def get_opportunity(oid: int, user=Depends(current_user)):
    row = opportunities.get_opp(user, oid)
    if not row:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    return row


@app.post("/api/opportunities", status_code=201)
def create_opportunity(body: OpportunityIn, user=Depends(current_user)):
    oid, errors = opportunities.create_opp(user, body.model_dump())
    if errors:
        bad_request(errors)
    return opportunities.get_opp(user, oid)


# ---------- follow-ups ----------

@app.get("/api/followups")
def get_followups(status: str = "", user=Depends(current_user)):
    return followups.list_followups(user, view="all", status=status)


@app.post("/api/followups", status_code=201)
def create_followup(body: FollowUpIn, user=Depends(current_user)):
    fid, errors = followups.create_followup(user, body.model_dump())
    if errors:
        bad_request(errors)
    return followups.get_followup(user, fid)


# ---------- reports ----------

@app.get("/api/reports/pipeline")
def pipeline(user=Depends(current_user)):
    by_stage, by_owner = reports.pipeline_report(user)
    return {"by_stage": by_stage, "by_owner": by_owner}
