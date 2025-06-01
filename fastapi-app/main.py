from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import os
from pathlib import Path
from fastapi.templating import Jinja2Templates
from typing import Optional
import logging
import time
from multiprocessing import Queue
from os import getenv
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler
from logging.handlers import QueueListener
from datetime import datetime

app = FastAPI()

# Prometheus 메트릭스 엔드포인트
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Loki 핸들러 + QueueListener 설정
log_queue = Queue(-1)
loki_handler = LokiQueueHandler(
    queue=log_queue,
    url=getenv("LOKI_ENDPOINT", "http://loki:3100/loki/api/v1/push"),
    tags={"application": "fastapi"},
    version="1",
)
queue_listener = QueueListener(log_queue, loki_handler)
queue_listener.start()

# Custom access logger 설정
custom_logger = logging.getLogger("custom.access")
custom_logger.setLevel(logging.INFO)
custom_logger.addHandler(logging.StreamHandler())  # 콘솔 출력
custom_logger.addHandler(loki_handler)

# 로그 미들웨어 등록
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    log_message = (
        f'{request.client.host} - "{request.method} {request.url.path} HTTP/1.1" '
        f'{response.status_code} {duration:.3f}s'
    )
    custom_logger.info(log_message)
    return response

# 경로 및 템플릿 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "todo.json"
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# JSON 파일 초기화
if not DATA_FILE.exists():
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump([], file)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def save_data(data):
    def datetime_handler(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False, default=datetime_handler)

# 모델 정의
class TodoItem(BaseModel):
    title: str
    description: str
    completed: bool = False
    tags: list[str] = []
    priority: str = "중간"
    due_date: Optional[datetime] = None

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None
    tags: Optional[list[str]] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None

# 라우팅
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/todos")
def get_todos():
    return load_data()

@app.post("/todos")
def add_todo(todo: TodoItem):
    todos = load_data()
    new_todo = {"id": len(todos) + 1, **todo.dict()}
    todos.append(new_todo)
    save_data(todos)
    return new_todo

@app.put("/todos/{todo_id}")
def update_todo(todo_id: int, updated_todo: TodoUpdate):
    todos = load_data()
    for todo in todos:
        if todo["id"] == todo_id:
            if updated_todo.title is not None:
                todo["title"] = updated_todo.title
            if updated_todo.description is not None:
                todo["description"] = updated_todo.description
            if updated_todo.completed is not None:
                todo["completed"] = updated_todo.completed
            if updated_todo.tags is not None:
                todo["tags"] = updated_todo.tags
            if updated_todo.priority is not None:
                todo["priority"] = updated_todo.priority
            if updated_todo.due_date is not None:
                todo["due_date"] = updated_todo.due_date
            save_data(todos)
            return todo
    raise HTTPException(status_code=404, detail="Todo not found")

@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    todos = load_data()
    todos = [todo for todo in todos if todo["id"] != todo_id]
    save_data(todos)
    return {"message": "Todo deleted successfully"}

@app.get("/todos/search")
def search_todos(q: str = Query(..., min_length=1)):
    todos = load_data()
    lower_q = q.lower()
    filtered = [
        todo for todo in todos
        if lower_q in todo["title"].lower()
        or lower_q in todo["description"].lower()
        or any(lower_q in tag.lower() for tag in todo["tags"])
    ]
    return filtered
