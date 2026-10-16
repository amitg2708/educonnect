"""
Test suite validating MongoDB database connectivity and operations.
"""

from django.test import TestCase
from django.db import connection
from django.conf import settings


class MongoDBConnectionTestCase(TestCase):
    databases = {"default"}

    def test_database_engine_is_official_mongodb(self):
        """
        Verify that the configured database engine is django_mongodb_backend.
        Ensures SQLite or PostgreSQL is not silently being used.
        """
        engine = connection.settings_dict.get("ENGINE")
        self.assertEqual(
            engine,
            "django_mongodb_backend",
            f"Expected engine 'django_mongodb_backend', but got '{engine}'.",
        )

    def test_mongodb_ping_success(self):
        """
        Verify active live connection by sending an admin ping command to MongoDB.
        """
        connection.ensure_connection()
        mongo_client = connection.connection
        self.assertIsNotNone(mongo_client, "MongoDB PyMongo client instance is None.")

        ping_result = mongo_client.admin.command("ping")
        self.assertEqual(
            ping_result.get("ok"),
            1.0,
            f"MongoDB ping failed: {ping_result}",
        )

    def test_mongodb_read_write_operation(self):
        """
        Verify actual document insertion and retrieval on MongoDB.
        """
        connection.ensure_connection()
        mongo_client = connection.connection
        db_name = connection.settings_dict.get("NAME")
        db = mongo_client[db_name]

        test_col = db["_connectivity_verification"]
        doc = {"test_key": "educonnect_probe", "status": "active"}

        # Write test document
        insert_res = test_col.insert_one(doc)
        self.assertIsNotNone(insert_res.inserted_id)

        # Read back test document
        retrieved = test_col.find_one({"_id": insert_res.inserted_id})
        self.assertEqual(retrieved.get("test_key"), "educonnect_probe")

        # Cleanup test document
        test_col.delete_one({"_id": insert_res.inserted_id})

    def test_mongodb_required_settings_preserved(self):
        """
        Verify router, default auto field, and migration modules are preserved.
        """
        self.assertEqual(
            settings.DEFAULT_AUTO_FIELD,
            "django_mongodb_backend.fields.ObjectIdAutoField",
        )
        self.assertIn(
            "django_mongodb_backend.routers.MongoRouter",
            settings.DATABASE_ROUTERS,
        )
        self.assertIn("admin", settings.MIGRATION_MODULES)
        self.assertIn("auth", settings.MIGRATION_MODULES)
        self.assertIn("contenttypes", settings.MIGRATION_MODULES)
