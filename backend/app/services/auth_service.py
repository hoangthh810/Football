from fastapi import HTTPException

from app.core.security import hash_password, verify_password, create_access_token
from app.db.database import get_database
from app.models.user_model import create_user_document, USER_COLLECTION


db = get_database()


async def handle_register(user_register) -> dict:
  data = user_register.model_dump()
  user_email = data["user_email"]
  user_fullname = data["user_fullname"]
  user_role = data["user_role"]
  user_password = data["user_password"]
  
  users_collection = db[USER_COLLECTION]
  existing_user = await users_collection.find_one({
    "user_email": user_email
  })
  if existing_user:
    raise HTTPException(status_code=400, detail="Email đã tồn tại")
  hashed_password = hash_password(user_password)
  user_doc = create_user_document(
    user_email=user_email,
    user_fullname=user_fullname,
    user_role=user_role,
    hashed_password=hashed_password
  )
  
  try:
    await users_collection.insert_one(user_doc)
    
  except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"Lỗi database, không thể lưu user vào database: {str(e)}",
    ) 
  
  return {
    'message': "Đăng ký tài khoản thành công"
  }
  
async def handle_login(user_login) -> dict:
    users_collection = db[USER_COLLECTION]

    user = await users_collection.find_one({
        "user_email": user_login.user_email
    })

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng",
        )

    hashed_password_user_in_db = user["hashed_password"]

    check_password = verify_password(
        user_login.user_password,
        hashed_password_user_in_db,
    )

    if not check_password:
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Tài khoản đã bị khóa",
        )

    user_id = str(user["_id"])
    access_token = create_access_token(user_id)

    return access_token