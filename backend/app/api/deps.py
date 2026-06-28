from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from bson import ObjectId
from bson.errors import InvalidId

from app.core.security import verify_access_token
from app.db.database import get_database
from app.models.user_model import USER_COLLECTION


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

db = get_database()
async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không chứa thông tin user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token chứa user_id không hợp lệ",
            headers={"WWW-Authenticate": "Bearer"},
        )

    users_collection = db[USER_COLLECTION]

    user = await users_collection.find_one({
        "_id": object_id
    })

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User không tồn tại",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa",
        )

    return user