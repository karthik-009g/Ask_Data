from sqlalchemy import inspect, create_engine
from pymongo import MongoClient

from app.db.system_store import metadata_collection
from app.services.connection_service import build_sqlalchemy_url, build_mongo_uri, resolve_mongo_database


def refresh_metadata(connection: dict) -> int:
    coll = metadata_collection()
    coll.delete_many({"connection_id": connection["connection_id"]})

    docs = []
    if connection["db_type"] in {"mysql", "postgresql"}:
        engine = create_engine(build_sqlalchemy_url(connection), pool_pre_ping=True)
        inspector = inspect(engine)
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            fks = inspector.get_foreign_keys(table_name)
            pk_constraint = inspector.get_pk_constraint(table_name) or {}
            pk_columns = set(pk_constraint.get("constrained_columns") or [])
            rel_map = {}
            for fk in fks:
                for col in fk.get("constrained_columns", []):
                    rel_map[col] = f"{fk.get('referred_table')}({','.join(fk.get('referred_columns', []))})"
            for column in columns:
                relation_parts = []
                if column["name"] in pk_columns:
                    relation_parts.append("PRIMARY_KEY")
                if rel_map.get(column["name"]):
                    relation_parts.append(f"FK->{rel_map.get(column['name'])}")
                docs.append(
                    {
                        "connection_id": connection["connection_id"],
                        "schema_name": connection.get("database_name"),
                        "table_name": table_name,
                        "column_name": column["name"],
                        "data_type": str(column.get("type")),
                        "relationship_info": "; ".join(relation_parts) if relation_parts else None,
                    }
                )
    elif connection["db_type"] == "mongodb":
        client = MongoClient(build_mongo_uri(connection))
        database = resolve_mongo_database(client, connection)
        for collection_name in database.list_collection_names():
            sample = database[collection_name].find_one() or {}
            for key, value in sample.items():
                docs.append(
                    {
                        "connection_id": connection["connection_id"],
                        "schema_name": database.name,
                        "table_name": collection_name,
                        "column_name": str(key),
                        "data_type": type(value).__name__,
                        "relationship_info": None,
                    }
                )

    if docs:
        coll.insert_many(docs)
    return len(docs)
