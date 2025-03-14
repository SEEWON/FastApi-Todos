from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import os
from pathlib import Path
from fastapi.templating import Jinja2Templates

app = FastAPI()

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
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# Todo 모델
class TodoItem(BaseModel):
    title: str
    description: str
    completed: bool = False

class TodoUpdate(BaseModel):
    title: str = None
    description: str = None
    completed: bool = None

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