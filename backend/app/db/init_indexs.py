from app.db.database import get_database
from app.models.user_model import USER_COLLECTION

db= get_database()
async def create_indexes():
    users_collection = db[USER_COLLECTION]

    await users_collection.create_index(
        "user_email",
        unique=True,
    )