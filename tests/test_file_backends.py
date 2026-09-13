"""The storage seam: three methods, and a refusal to guess.

`lib/file_store` always claimed a real deployment "swaps this for S3/GCS/
on-disk plus a DB for the URL map" — in a docstring, with no seam to do it
through. This pins the seam that now exists, because the value of it is
entirely that someone can point the app at R2 without touching the canvas,
the page, or the routes.
"""

from __future__ import annotations

import os

import pytest

from lib import file_backends, file_store


@pytest.fixture(autouse=True)
def _isolated():
    file_backends.reset_for_tests()
    os.environ.pop("EXCALIDRAW_FILE_BACKEND", None)
    yield
    file_backends.reset_for_tests()
    os.environ.pop("EXCALIDRAW_FILE_BACKEND", None)
    file_store.clear()


class TestTheDefault:
    def test_it_is_memory_and_nothing_has_to_be_configured(self):
        assert file_backends.backend().describe()["name"] == "memory"

    def test_it_round_trips(self):
        b = file_backends.backend()
        url = b.put("k1", "image/gif", b"GIF89a-ish")
        assert url.endswith("/k1")
        assert b.get("k1") == ("image/gif", b"GIF89a-ish")

    def test_it_reports_the_two_facts_that_decide_deployability(self):
        # Not vanity fields: "lost on restart" and "per-worker" are exactly
        # why the memory backend is a demo default and not a deployment.
        info = file_backends.backend().describe()
        assert info["survives_restart"] is False
        assert info["shared_between_workers"] is False


class TestDisk:
    def test_it_survives_a_new_backend_object(self, tmp_path):
        first = file_backends.DiskBackend(str(tmp_path))
        first.put("k2", "text/plain", b"hello")
        # A different instance is the closest in-process stand-in for the
        # other gunicorn worker, which is the fault this backend fixes.
        second = file_backends.DiskBackend(str(tmp_path))
        assert second.get("k2") == ("text/plain", b"hello")

    def test_the_mime_type_travels_with_the_bytes(self, tmp_path):
        # Guessing it back from the extension loses application/json vs
        # text/plain, and the drawer preview picks its renderer by mime.
        b = file_backends.DiskBackend(str(tmp_path))
        b.put("note", "application/json", b"{}")
        assert b.get("note")[0] == "application/json"

    def test_a_missing_key_is_none_not_an_exception(self, tmp_path):
        assert file_backends.DiskBackend(str(tmp_path)).get("nope") is None

    @pytest.mark.parametrize("key", ["../escape", "a/b", "", ".", ".."])
    def test_a_traversing_key_is_refused(self, tmp_path, key):
        # Keys are minted by this app, never by a visitor — but a traversal
        # here writes outside the root, so it is refused rather than trusted.
        b = file_backends.DiskBackend(str(tmp_path))
        with pytest.raises(ValueError):
            b.put(key, "text/plain", b"x")

    def test_it_reports_that_it_survives_and_is_shared(self, tmp_path):
        info = file_backends.DiskBackend(str(tmp_path)).describe()
        assert info["survives_restart"] is True
        assert info["shared_between_workers"] is True


class TestSelectingOne:
    def test_the_env_var_chooses(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXCALIDRAW_FILE_BACKEND", "disk")
        monkeypatch.setenv("EXCALIDRAW_FILE_DIR", str(tmp_path))
        assert file_backends.backend().describe()["name"] == "disk"

    def test_an_unknown_name_raises_rather_than_falling_back(self, monkeypatch):
        """The property worth having.

        A storage backend that silently is not the one you configured is worse
        than a boot failure: the site comes up, uploads appear to work, and
        the bytes are somewhere else. Naming the known ones in the message
        makes the typo obvious.
        """
        monkeypatch.setenv("EXCALIDRAW_FILE_BACKEND", "r2-typo")
        with pytest.raises(RuntimeError) as exc:
            file_backends.backend()
        assert "r2-typo" in str(exc.value)
        assert "memory" in str(exc.value)

    def test_a_custom_backend_can_be_registered(self, monkeypatch):
        # The whole point of the seam: a CDN backend returns a URL this app
        # does not serve, and nothing above storage notices.
        class Cdn(file_backends.FileBackend):
            name = "cdn-test"

            def put(self, key, mime_type, data):
                return self.url_for(key)

            def get(self, key):
                return None

            def url_for(self, key):
                return f"https://cdn.example/{key}"

        file_backends.register_backend("cdn-test", Cdn)
        monkeypatch.setenv("EXCALIDRAW_FILE_BACKEND", "cdn-test")
        b = file_backends.backend()
        assert b.put("x", "image/gif", b"g") == "https://cdn.example/x"
        assert b.get("x") is None


class TestTheStoreNeverReEncodes:
    def test_bytes_come_back_identical(self):
        """Rasterisation is a BROWSER behaviour, not a storage one.

        Worth pinning because the GIF bug looked like storage: what came back
        from a URL was a still PNG. It was a still PNG before it ever reached
        Python, and this asserts the storage half is not the suspect.
        """
        raw = bytes(range(256)) * 8
        b = file_backends.backend()
        b.put("blob", "application/octet-stream", raw)
        assert b.get("blob")[1] == raw
