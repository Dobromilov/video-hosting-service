from typing import Optional

from authx.exceptions import MissingTokenError, RevokedTokenError
from fastapi import Depends, HTTPException, status, APIRouter, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from authx import AuthX, AuthXConfig
from pydantic import BaseModel
from datetime import timedelta
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


config = AuthXConfig(
    JWT_ALGORITHM="HS256",
    JWT_SECRET_KEY="your-secret-key-123",  # Обязательно поменяйте в продакшене!
    JWT_TOKEN_LOCATION=["cookies"],  # Только cookies
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=30),
    #JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=7),
    JWT_COOKIE_SECURE=False,  # True для HTTPS
    JWT_COOKIE_CSRF_PROTECT=False,  # Упрощаем для разработки
)

auth = AuthX(config=config)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Модели
class Token(BaseModel):
    access_token: str
    token_type: str



class UserCreate(BaseModel):
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


# Вспомогательные функции
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str):
    return pwd_context.hash(password)


def get_user(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def authenticate_user(db: Session, email: str, password: str):
    user = get_user(db, email)
    if not user:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user


# Маршруты аутентификации
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user(db, user_data.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    db_email = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user_data.password)
    db_user = models.User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return {"message": "User created successfully"}


@router.post("/token", response_model=Token)
async def login(
        response: Response,
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)# username == email
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials"
        )

    access_token = auth.create_access_token(uid=str(user.id))
    #refresh_token = auth.create_refresh_token(uid=str(user.id))

    auth.set_access_cookies(access_token, response)
    #auth.set_refresh_cookies(refresh_token, response)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


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

@router.post("/logout")  # Меняем POST на GET
async def logout(response: Response):
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    auth.unset_cookies(response)
    return response



async def get_current_user(
        request: Request,
        db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Получаем токен из запроса
        token = auth.get_token_from_request(request, optional=False)
        print(f"Token received: {token}")  # Для отладки

        # Декодируем токен
        payload = auth.verify_token(token)
        print(f"Token payload: {payload}")  # Для отладки

        # Получаем идентификатор пользователя (используем 'sub' вместо 'uid')
        user_id = payload.sub
        if not user_id:
            print("No user_id in payload")  # Для отладки
            raise credentials_exception

        # Ищем пользователя в базе
        user = db.query(models.User).filter(models.User.id == int(user_id)).first()
        if not user:
            print(f"User not found with id: {user_id}")  # Для отладки
            raise credentials_exception

        return user

    except MissingTokenError:
        print("Token is missing")  # Для отладки
        raise credentials_exception
    except RevokedTokenError:
        print("Token has been revoked")  # Для отладки
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"Authentication error: {str(e)}")  # Для отладки
        raise credentials_exception


async def get_current_active_user(current_user: models.User = Depends(get_current_user_optional)):

    return current_user
