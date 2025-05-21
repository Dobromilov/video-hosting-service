from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status
from typing import Annotated, Optional
from sqlalchemy.orm import Session, joinedload
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
    # Получаем видео с автором
    video = db.query(models.Video) \
        .options(joinedload(models.Video.author)) \
        .filter(models.Video.id == video_id) \
        .first()

    if not video:
        raise HTTPException(status_code=404, detail="Видео не найдено")

    # Получаем комментарии с пользователями и реакциями
    comments_query = db.query(models.Comment) \
        .options(
        joinedload(models.Comment.user)
        #joinedload(models.Comment.likes)
    ) \
        .filter(models.Comment.video_id == video_id) \
        .order_by(models.Comment.created_at.desc())

    # Получаем все комментарии
    all_comments = comments_query.all()

    # # Собираем ID комментариев и реакции пользователя
    comment_ids = [c.id for c in all_comments]
    user_reactions = {}

    if user:
        reactions = db.query(models.CommentLike) \
            .filter(
            models.CommentLike.comment_id.in_(comment_ids),
            models.CommentLike.user_id == user.id
        ) \
            .all()
        user_reactions = {r.comment_id: r.is_like for r in reactions}

    # Формируем древовидную структуру комментариев
    def build_comment_tree(comments, parent_id=None):
        result = []
        for comment in comments:
            if comment.parent_comment_id == parent_id:
                # Устанавливаем пользовательскую реакцию
                comment.user_reaction = user_reactions.get(comment.id)
                # Рекурсивно получаем ответы
                comment.replies = build_comment_tree(comments, comment.id)
                result.append(comment)
        return result

    # Строим иерархию комментариев
    comments_tree = build_comment_tree(all_comments)

    # Обновляем счетчик просмотров
    db.query(models.Video) \
        .filter(models.Video.id == video_id) \
        .update({models.Video.views: models.Video.views + 1})
    db.commit()

    return templates.TemplateResponse(
        "video.html",
        {
            "request": request,
            "video": video,
            "author": video.author,
            "comments": comments_tree,
            "user": user
        }
    )

def format_date(value, format_str="%d.%m.%Y"):
    if isinstance(value, datetime):
        return value.strftime(format_str)
    return value

templates = Jinja2Templates(directory="templates")
templates.env.filters["date"] = format_date

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)