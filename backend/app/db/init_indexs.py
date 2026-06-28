from app.db.database import get_database
from app.models.user_model import USER_COLLECTION
from pymongo.errors import OperationFailure

db = get_database()


async def create_indexes():
    users_collection = db[USER_COLLECTION]
    analysis_jobs_collection = db["analysis_jobs"]
    uploads_collection = db["uploads"]

    await users_collection.create_index(
        "user_email",
        unique=True,
    )

    try:
        await analysis_jobs_collection.drop_index("user_id_1")
    except OperationFailure:
        pass

    await analysis_jobs_collection.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="analysis_jobs_user_created_at_idx",
    )

    await analysis_jobs_collection.create_index(
        "batch_id",
        name="analysis_jobs_batch_id_idx",
    )

    await uploads_collection.create_index(
        "batch_id",
        name="uploads_batch_id_idx",
    )
