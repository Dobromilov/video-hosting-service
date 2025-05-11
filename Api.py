import shutil
from typing import Optional
from fastapi import Depends, HTTPException, status, APIRouter, Request, Response, Form, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from datetime import timedelta
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import time
import os



import models
from models import User
from Auth import auth, pwd_context

router = APIRouter(
    prefix="/api",
    tags=["api"]
)
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


# Модели
class VideoCreate(BaseModel):
    username: str
    email: str
    password: str
    profile_picture: str = None

def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/check-username")
async def check_username(username: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.username == username).first()
    return {"exists": user is not None}




async def get_current_user_optional(
        request: Request,
        db: Session = Depends(get_db)
) -> Optional[models.User]:
    try:
        token = await auth._get_token_from_request(request, optional=True)
        if not token:
            return None

        payload = auth._decode_token(token.token)
        user = db.query(models.User).filter(models.User.id == int(payload.sub)).first()
        return user
    except Exception:
        return None


ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

@router.post("/update-profile")
async def update_profile(
    username: str = Form(...),
    profile_picture: UploadFile = File(None),
    keep_current_avatar: bool = Form(False),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):

    # Валидация имени пользователя
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")

    if username != user.username:
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already taken")

    # Обработка аватара
    if profile_picture and not keep_current_avatar:
        # Проверка размера файла
        file_size = profile_picture.file.seek(0, 2)
        profile_picture.file.seek(0)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large")

        # Проверка расширения
        file_ext = os.path.splitext(profile_picture.filename)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Генерация имени и сохранение
        filename = f"{user.id}_{int(time.time())}{file_ext}"
        filepath = f"static/profiles_pictures/{filename}"

        os.makedirs("static/profiles_pictures", exist_ok=True)

        try:
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(profile_picture.file, buffer)

            # Удаление старого аватара
            if user.profile_picture:
                old_file = f"static/profiles_pictures/{user.profile_picture}"
                if os.path.exists(old_file):
                    os.remove(old_file)

            user.profile_picture = filename
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # Обновление данных
    user.username = username
    db.commit()

    return {"success": True, "new_username": username, "avatar": user.profile_picture}


@router.post("/change-password")
async def change_password(
        changePasswordRequest: ChangePasswordRequest,
        user: User = Depends(get_current_user_optional),
        db: Session = Depends(get_db)
):

    # Проверка совпадения паролей
    if changePasswordRequest.new_password != changePasswordRequest.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароли не совпадают"
        )

    # Проверка длины пароля
    if len(changePasswordRequest.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль должен содержать минимум 8 символов"
        )

    # Проверка текущего пароля
    if not pwd_context.verify(changePasswordRequest.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный текущий пароль"
        )

    # Обновление пароля
    try:
        user.password_hash = pwd_context.hash(changePasswordRequest.new_password)
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении пароля: {str(e)}"
        )

@router.post("/upload-video")
async def upload_video(
    title: str = Form(...),
    description: str = Form(None),
    video_file: UploadFile = File(...),
    thumbnail: UploadFile = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Создание папок
        os.makedirs("static/videos", exist_ok=True)
        os.makedirs("static/thumbnails", exist_ok=True)

        # Сохранение видео
        video_filename = f"video_{user.id}_{int(time.time())}.mp4"
        video_path = f"static/videos/{video_filename}"
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        # Сохранение обложки
        thumbnail_filename = "default-thumbnail.jpg"
        if thumbnail and thumbnail.content_type.startswith('image/'):
            thumbnail_filename = f"thumb_{user.id}_{int(time.time())}.jpg"
            thumbnail_path = f"static/thumbnails/{thumbnail_filename}"
            with open(thumbnail_path, "wb") as buffer:
                shutil.copyfileobj(thumbnail.file, buffer)

        # Создание записи в БД
        new_video = models.Video(
            title=title,
            description=description,
            filepath=video_filename,
            thumbnail=thumbnail_filename,
            user_id=user.id,
            created_at=datetime.now()
        )
        db.add(new_video)
        db.commit()

        return {"status": "success"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))