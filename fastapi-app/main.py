from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler
from logging.handlers import QueueListener
from multiprocessing import Queue
from pathlib import Path
from typing import Optional
from datetime import datetime
import logging
import json
import os
import time

# FastAPI 초기화
app = FastAPI()

# Prometheus 메트릭스 노출
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# 로그 큐 및 Loki 핸들러 설정
log_queue = Queue(-1)
loki_handler = LokiQueueHandler(
    queue=log_queue,
    url=os.getenv("LOKI_ENDPOINT", "http://loki:3100/loki/api/v1/push"),
    tags={"application": "fastapi"},
    version="1"
)

queue_listener = QueueListener(log_queue, loki_handler)
queue_listener.start()

# Logger 정의
logger = logging.getLogger("custom.access")
logger.setLevel(logging.INFO)
logger.addHandler(loki_handler)  # Loki로만 전송 (StreamHandler는 생략해도 무방)

# 초기 로그 (Grafana에서 테스트용으로 확인 가능)
logger.info("🔵 FastAPI 애플리케이션 시작됨")

# 미들웨어로 모든 요청 로그 처리
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    log_message = f'{request.client.host} - "{request.method} {request.url.path}" {response.status_code} {duration:.3f}s'
    logger.info(log_message)

    return response

# 템플릿 및 데이터 파일 경로
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_FILE = BASE_DIR / "todo.json"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# JSON 초기화
if not DATA_FILE.exists():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    def datetime_handler(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError("Not JSON serializable")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=datetime_handler)

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

# 라우터 정의
@app.get("/", response_class=HTMLResponse)
def root(request: Request):
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
def update_todo(todo_id: int, updated: TodoUpdate):
    todos = load_data()
    for todo in todos:
        if todo["id"] == todo_id:
            if updated.title is not None: todo["title"] = updated.title
            if updated.description is not None: todo["description"] = updated.description
            if updated.completed is not None: todo["completed"] = updated.completed
            if updated.tags is not None: todo["tags"] = updated.tags
            if updated.priority is not None: todo["priority"] = updated.priority
            if updated.due_date is not None: todo["due_date"] = updated.due_date
            save_data(todos)
            return todo
    raise HTTPException(status_code=404, detail="Todo not found")

@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    todos = load_data()
    todos = [t for t in todos if t["id"] != todo_id]
    save_data(todos)
    return {"message": "삭제 완료"}

@app.get("/todos/search")
def search(q: str = Query(..., min_length=1)):
    todos = load_data()
    q = q.lower()
    return [
        t for t in todos if
        q in t["title"].lower()
        or q in t["description"].lower()
        or any(q in tag.lower() for tag in t["tags"])
    ]
