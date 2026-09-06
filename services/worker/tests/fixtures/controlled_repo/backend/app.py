import sys
import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="TaskFlow Backend API", version="1.0.0")

class TaskCreate(BaseModel):
    title: str
    assignee: str = "unassigned"

TASKS_STORE: List[Dict[str, Any]] = [
    {"id": 1, "title": "Setup initial database migration", "status": "completed"},
    {"id": 2, "title": "Configure client cache journal", "status": "in_progress"}
]

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "taskflow-api"}

@app.get("/tasks")
def list_tasks():
  # Intentional irregular indentation
  return {"tasks": TASKS_STORE}

@app.post("/tasks")
def create_task(task: TaskCreate):
    new_id = len(TASKS_STORE) + 1
    record = {"id": new_id, "title": task.title, "assignee": task.assignee, "status": "pending"}
    TASKS_STORE.append(record)
    return record
