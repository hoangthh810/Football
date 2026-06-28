from app.db.database import get_database
from app.core.security import verify_access_token

db = get_database()

def get_current_user(token: str) -> dict: 
    