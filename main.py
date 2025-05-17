from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status
from typing import Annotated, Optional
from sqlalchemy.orm import Session
import models
import Auth
from Auth import get_current_user, get_current_active_user
import Api

# Создание таблиц
models.Base.metadata.create_all(bind=models.engine)

app = FastAPI()
app.include_router(Api.router)
app.include_router(Auth.router)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Зависимости
def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[models.User, Depends(get_current_active_user)]

@app.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    user: Optional[models.User] = Depends(Auth.get_current_user_optional)
):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "main.html",
        {
            "request": request,
            "user": user,  # Будет None если пользователь не авторизован
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request,
                     user: Optional[models.User] = Depends(Auth.get_current_user_optional)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request,
                        user: Optional[models.User] = Depends(Auth.get_current_user_optional)
                        ):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: user_dependency, db: db_dependency):
    if user:
        videos = await Api.get_user_videos(user.id, db)
        return templates.TemplateResponse(
            "profile.html",
            {"request": request, "user": user, "user_videos": videos}
        )
    else:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/video/{video_id}", response_class=HTMLResponse)
async def video_page(
    request: Request,
    video_id: int,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(Auth.get_current_user_optional)
):
    # Получаем видео
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")

    # Получаем автора видео отдельным запросом
    author = db.query(models.User).filter(models.User.id == video.user_id).first()

    # Получаем комментарии отдельным запросом
    comments = db.query(models.Comment)\
        .filter(models.Comment.video_id == video_id)\
        .all()

    # Увеличиваем счетчик просмотров
    video.views += 1
    db.commit()

    return templates.TemplateResponse(
        "video.html",
        {
            "request": request,
            "video": video,
            "author": author,  # Передаем автора отдельно
            "comments": comments,  # Передаем комментарии отдельно
            "user": user
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)