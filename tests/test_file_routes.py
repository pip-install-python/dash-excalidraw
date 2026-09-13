"""The blob routes /file-uploads depends on.

THE BUG, measured 2026-09-12: `lib/file_routes.py` was never imported by
anything. The module existed, it was correct, and it was dead — so the routes
were registered on NO backend. Every URL that page handed the canvas was
therefore answered by Dash's own page router:

    GET /excalidraw-files/nope   ->  200, text/html, 48,882 bytes

which is the site's HTML shell, not the file. Externalized images fell back to
Excalidraw's inline copies (so nobody noticed), and the GIF auto-embed framed
that HTML shell in an iframe instead of an animation — which is how it
surfaced. After the fix the same request answers 404: the route exists and
says honestly that the blob does not.

The old docstring claimed FastAPI "degrades to Excalidraw's own inline copies,
which is a visual no-op". Wrong twice: nothing registered them on Flask
either, and the degradation is not a no-op on a page whose entire subject is
getting the bytes OUT of the canvas. FastAPI is the local dev backend here, so
it is the one that had to work.
"""

from __future__ import annotations

import base64

import pytest

from lib import file_routes, file_store

# A real 1x1 GIF. Small enough to inline, real enough that the Content-Type
# assertion below is about an actual image rather than a byte string.
GIF_BYTES = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@pytest.fixture
def stored_gif():
    file_id = "test-gif-entry"
    file_store.put(file_id, "image/gif", GIF_BYTES)
    yield file_id
    file_store.clear()


class TestTheRoutesAreReachableOnFastAPI:
    """The backend this repo runs locally, and the one that was excluded."""

    @pytest.fixture
    def client(self):
        fastapi = pytest.importorskip("fastapi")
        starlette_testclient = pytest.importorskip("starlette.testclient")

        server = fastapi.FastAPI()
        # `register` takes the Dash app and reaches for `.server`; a stand-in
        # with just that attribute is enough and keeps this test off the
        # whole-app boot path.
        attached = file_routes.register(type("App", (), {"server": server})())
        assert attached == "fastapi", (
            f"register() returned {attached!r} for a FastAPI server — the "
            f"routes would not be mounted on this repo's own dev backend"
        )
        return starlette_testclient.TestClient(server)

    def test_the_bytes_come_back_with_their_own_mime(self, client, stored_gif):
        r = client.get(f"{file_store.FILE_URL_PREFIX}/{stored_gif}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/gif")
        assert r.content == GIF_BYTES

    def test_a_missing_blob_is_404_not_the_site(self, client):
        """The exact shape of the bug.

        Before the fix this request reached Dash's page router and came back
        200 with the site's HTML. A 404 here is what proves the route is the
        one answering.
        """
        r = client.get(f"{file_store.FILE_URL_PREFIX}/definitely-not-a-file")
        assert r.status_code == 404
        assert "<html" not in r.text.lower()

    def test_the_viewer_wraps_the_gif_in_html(self, client, stored_gif):
        # The embeddable's iframe points here rather than at the raw GIF:
        # framing the asset directly trips Chromium's same-URL frame check,
        # and an <img> inside a tiny document does not.
        r = client.get(f"{file_store.FILE_URL_PREFIX}/{stored_gif}/viewer")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert f'<img src="{file_store.FILE_URL_PREFIX}/{stored_gif}"' in r.text

    def test_a_missing_viewer_is_404_too(self, client):
        r = client.get(f"{file_store.FILE_URL_PREFIX}/nope/viewer")
        assert r.status_code == 404


class TestTheRoutesAreActuallyWiredUp:
    """A correct module nobody imports is the bug this file exists for."""

    def test_run_py_registers_them(self):
        from pathlib import Path

        run_py = (Path(__file__).resolve().parent.parent / "run.py").read_text(
            encoding="utf-8"
        )
        assert "file_routes.register(app)" in run_py, (
            "nothing calls register(), so the routes are mounted nowhere and "
            "/file-uploads hands the canvas URLs that resolve to the SPA"
        )

    def test_a_failure_to_mount_is_loud(self):
        from pathlib import Path

        run_py = (Path(__file__).resolve().parent.parent / "run.py").read_text(
            encoding="utf-8"
        )
        # Silence is how this survived. An unrecognised backend must say so at
        # boot rather than leave a page quietly broken.
        assert "blob routes NOT" in run_py


class TestTheViewerBodyChoosesByType:
    def test_an_image_becomes_an_img(self):
        assert "<img" in file_routes._viewer_body("image/gif", "/x")

    def test_a_pdf_becomes_an_iframe(self):
        assert "<iframe" in file_routes._viewer_body("application/pdf", "/x")

    def test_anything_else_says_so_rather_than_rendering_nothing(self):
        body = file_routes._viewer_body("application/zip", "/x")
        assert "application/zip" in body
        assert "<img" not in body
