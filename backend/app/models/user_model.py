from datetime import datetime, timezone

USER_COLLECTION = "users"

def create_user_document(user_email: str, user_fullname: str, user_role: str, hashed_password: str) -> dict:
  return {
      "user_email": user_email,
      "user_fullname": user_fullname,
      "user_role": user_role,
      "hashed_password": hashed_password,
      "is_active": True,
      "created_at": datetime.now(timezone.utc),
      "updated_at": datetime.now(timezone.utc),
  }