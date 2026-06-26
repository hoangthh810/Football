from pymongo import AsyncMongoClient
from app.core.config import settings


client = AsyncMongoClient(settings.MONGODB_URL)

database = client[settings.DATABASE_NAME]


def get_database():
    return database