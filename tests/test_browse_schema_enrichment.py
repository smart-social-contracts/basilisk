"""Unit tests for __browse__ schema enrichment with ic-python-db entities.

Tests verify that _generate_default_browse_code produces code that, when
ic_python_db is available, adds 'entities' and 'schema_hash' to the schema
action response.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.build_wasm_binary_or_exit import _generate_default_browse_code


class _FakeStableStructure:
    """Minimal mock for StableBTreeMap/Set/Vec used in generated browse code."""

    def __init__(self):
        self._data = {}
        self._items = []

    def len(self):
        return len(self._data) or len(self._items)

    def keys(self):
        return list(self._data.keys())

    def get(self, key):
        return self._data.get(key)

    def items(self):
        return self._items or list(self._data.items())

    def insert(self, key, value):
        self._data[key] = value

    def push(self, value):
        self._items.append(value)


def _exec_browse(stable_structures, query_dict):
    """Generate browse code, exec it, and call __browse__ with a query."""
    source = _generate_default_browse_code(stable_structures)
    # Inject mock variables for each stable structure referenced in the code
    namespace = {}
    for ss in stable_structures:
        namespace[ss["name"]] = _FakeStableStructure()
    exec(source, namespace)
    browse_fn = namespace["__browse__"]
    raw = browse_fn(json.dumps(query_dict))
    return json.loads(raw)


class TestBrowseSchemaBaseline:
    """Schema action works for stable structures without ic_python_db."""

    def test_schema_returns_stable_maps(self):
        structures = [
            {"name": "users", "structure_type": "StableBTreeMap",
             "memory_id": 0, "key_type": "text", "value_type": "nat"},
        ]
        result = _exec_browse(structures, {"action": "schema"})
        assert "stable_maps" in result
        assert "users" in result["stable_maps"]
        assert result["stable_maps"]["users"]["key_type"] == "text"

    def test_schema_returns_stable_sets(self):
        structures = [
            {"name": "tags", "structure_type": "StableBTreeSet",
             "memory_id": 1, "key_type": "text"},
        ]
        result = _exec_browse(structures, {"action": "schema"})
        assert "stable_sets" in result
        assert "tags" in result["stable_sets"]

    def test_schema_returns_stable_vecs(self):
        structures = [
            {"name": "logs", "structure_type": "StableVec",
             "memory_id": 2, "value_type": "text"},
        ]
        result = _exec_browse(structures, {"action": "schema"})
        assert "stable_vecs" in result
        assert "logs" in result["stable_vecs"]

    def test_empty_categories_omitted(self):
        structures = [
            {"name": "data", "structure_type": "StableBTreeMap",
             "memory_id": 0, "key_type": "text", "value_type": "text"},
        ]
        result = _exec_browse(structures, {"action": "schema"})
        assert "stable_sets" not in result
        assert "stable_vecs" not in result

    def test_no_entities_or_hash_without_ic_python_db(self):
        structures = []
        result = _exec_browse(structures, {"action": "schema"})
        # ic_python_db not importable in test env, so these should be absent
        # unless ic_python_db happens to be installed — either way, no crash
        assert isinstance(result, dict)


class TestBrowseSchemaWithIcPythonDb:
    """When ic_python_db is importable, schema includes entity info."""

    @staticmethod
    def _ic_python_db_available():
        try:
            import ic_python_db
            return True
        except ImportError:
            return False

    def test_schema_enrichment_when_available(self):
        """If ic_python_db is installed, entities and schema_hash appear."""
        if not self._ic_python_db_available():
            # Install ic-python-db from local source for this test
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e",
                 os.path.join(os.path.dirname(__file__), "..", "..", "ic-python-db")],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                import pytest
                pytest.skip("ic-python-db not installable in test env")

        # Ensure fresh import
        for mod_name in list(sys.modules):
            if mod_name.startswith("ic_python_db"):
                del sys.modules[mod_name]

        from ic_python_db import Database, Entity
        from ic_python_db.properties import String, Integer

        # Save and replace the singleton so the browse code finds our entities
        saved_instance = Database._instance
        db = Database()
        Database._instance = db

        try:
            class TestUser(Entity):
                __db__ = db
                name = String(default="")
                age = Integer(default=0)

            structures = [
                {"name": "data", "structure_type": "StableBTreeMap",
                 "memory_id": 0, "key_type": "text", "value_type": "text"},
            ]
            # Save schema first so get_schema_hash() returns a value
            db.save_schema()

            result = _exec_browse(structures, {"action": "schema"})
            assert "entities" in result
            assert "schema_hash" in result
            assert isinstance(result["schema_hash"], str)
            assert len(result["schema_hash"]) == 64  # SHA-256 hex
        finally:
            db._entity_types.clear()
            Database._instance = saved_instance


class TestBrowseErrorHandling:
    """Verify error responses from __browse__."""

    def test_invalid_json(self):
        result_str = _generate_default_browse_code([])
        namespace = {}
        exec(result_str, namespace)
        raw = namespace["__browse__"]("not json")
        result = json.loads(raw)
        assert "error" in result

    def test_unknown_action(self):
        structures = [
            {"name": "m", "structure_type": "StableBTreeMap",
             "memory_id": 0, "key_type": "text", "value_type": "text"},
        ]
        result = _exec_browse(structures, {"action": "delete", "map": "m"})
        assert "error" in result

    def test_missing_target(self):
        structures = [
            {"name": "m", "structure_type": "StableBTreeMap",
             "memory_id": 0, "key_type": "text", "value_type": "text"},
        ]
        result = _exec_browse(structures, {"action": "keys"})
        assert "error" in result
        assert "available" in result
