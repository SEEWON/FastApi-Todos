from fastapi import FastAPI, HTTPException, Request
from fastapi import Query
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
from fastapi import Request
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler
from datetime import datetime

app = FastAPI()

# Prometheus 메트릭스 엔드포인트 (/metrics)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Loki 핸들러 + QueueListener 설정
log_queue = Queue(-1)
loki_handler = LokiQueueHandler(
    queue=log_queue,
    url=getenv("LOKI_ENDPOINT"),
    tags={"application": "fastapi"},
    version="1",
)


# Custom access logger 설정
custom_logger = logging.getLogger("custom.access")
custom_logger.setLevel(logging.INFO)
custom_logger.addHandler(loki_handler)

async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time  # Compute response time

    log_message = (
        f'{request.client.host} - "{request.method} {request.url.path} HTTP/1.1" {response.status_code} {duration:.3f}s'
    )

    # **Only log if duration exists**
    if duration:
        custom_logger.info(log_message)

    return response

app.middleware("http")(log_requests)

# 프로젝트 경로 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "todo.json"
TEMPLATES_DIR = BASE_DIR / "templates"

# 템플릿 설정
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# JSON 파일 초기화 (빈 배열)
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

# Todo 모델
class TodoItem(BaseModel):
    title: str
    description: str
    completed: bool = False
    tags: list[str] = []
    priority: str = "중간"  # 높음, 중간, 낮음 중 하나
    due_date: Optional[datetime] = None

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None
    tags: Optional[list[str]] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None


# 기본 페이지 제공 (프론트엔드 렌더링)
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 할 일 목록 가져오기
@app.get("/todos")
def get_todos():
    return load_data()

# 새로운 할 일 추가
@app.post("/todos")
def add_todo(todo: TodoItem):
    todos = load_data()
    new_todo = {"id": len(todos) + 1, **todo.dict()}
    todos.append(new_todo)
    save_data(todos)
    return new_todo


# 특정 할 일 수정 (부분 업데이트 허용)
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
            if updated_todo.tags is not None:  # 👈 이 부분 추가
                todo["tags"] = updated_todo.tags
            if updated_todo.priority is not None:
                todo["priority"] = updated_todo.priority
            if updated_todo.due_date is not None:
                todo["due_date"] = updated_todo.due_date
            save_data(todos)
            return todo
    raise HTTPException(status_code=404, detail="Todo not found")


# 특정 할 일 삭제
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