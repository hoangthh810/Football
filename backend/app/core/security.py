from app.core.config import settings
import bcrypt
import datetime
import jwt

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
EXP_HOURS = settings.ACCESS_TOKEN_EXPIRE_HOURS


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode("utf-8")
    return hashed_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    hashed_password_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)


def create_access_token(user_id: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)

    payload = {
        "sub": user_id,
        "exp": now + datetime.timedelta(hours=EXP_HOURS),
        "iat": now,
    }

    token = jwt.encode(
        payload=payload,
        key=SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return token


def verify_access_token(token: str) -> dict | None:
    try:
        decoded_payload = jwt.decode(
            jwt=token,
            key=SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        return decoded_payload

    except jwt.ExpiredSignatureError:
        return None

    except jwt.InvalidTokenError:
        return None