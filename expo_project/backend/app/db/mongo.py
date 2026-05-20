from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
import certifi

from app.core.config import settings


class UserDoc(dict):
    """
    MongoDB user document shape.
    Fields: _id (ObjectId), organisation, email, full_name, hashed_password, role, created_at
    Helper properties for convenient attribute-style access used by services.
    """

    @property
    def id(self) -> str:
        return str(self["_id"])

    @property
    def role(self) -> str:
        return self["role"]

    @property
    def organisation(self) -> str:
        return self.get("organisation", "")


_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        if not settings.mongo_url:
            raise RuntimeError("MONGO_URL is not configured. Set it to your MongoDB Atlas connection string.")
        uri = settings.mongo_url.strip()
        kwargs: dict = {
            "serverSelectionTimeoutMS": 10000,
            "connectTimeoutMS": 10000,
            "socketTimeoutMS": 20000,
        }
        if uri.startswith("mongodb+srv://") or "tls=true" in uri.lower() or "ssl=true" in uri.lower():
            kwargs["tlsCAFile"] = certifi.where()

        _client = MongoClient(uri, **kwargs)
        _client.admin.command("ping")
    return _client


def get_users_collection() -> Collection:
    client = get_mongo_client()
    db = client.get_default_database(default="auth_db")
    coll = db["users"]

    try:
        index_info = coll.index_information()
        legacy_email_index = index_info.get("email_1")
        has_compound_index = "organisation_1_email_1" in index_info

        if legacy_email_index and legacy_email_index.get("unique") and not has_compound_index:
            coll.drop_index("email_1")

        coll.create_index([("organisation", ASCENDING), ("email", ASCENDING)], unique=True)
    except Exception:
        pass

    return coll


def find_user_by_id(user_id: str) -> UserDoc | None:
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    coll = get_users_collection()
    doc = coll.find_one({"_id": oid})
    return UserDoc(doc) if doc else None


def find_user_by_email(email: str, organisation: str | None = None) -> UserDoc | None:
    coll = get_users_collection()
    query: dict = {"email": email}
    if organisation is not None:
        query["organisation"] = organisation
    doc = coll.find_one(query)
    return UserDoc(doc) if doc else None
