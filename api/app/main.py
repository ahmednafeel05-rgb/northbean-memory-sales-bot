import os

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel

from . import agent

app = FastAPI(title="Northbean Sales Bot API")


@app.get("/health")
def health():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return ChatResponse(reply=agent.run_turn(req.message))
