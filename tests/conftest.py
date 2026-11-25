import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PARAGON_FAMILY_FILE"] = os.path.join(__import__("tempfile").mkdtemp(prefix="family-"), "finish")  # never the real choice
# Tests never touch the real Recycle Bin: PR7P_TRASH points Delete at a folder of its own (per test, below).
os.environ["PR7P_TRASH"] = tempfile.mkdtemp(prefix="pr7p-trash-")


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    # Tests never write the real settings: QSettings goes to INI files in a temp folder.
    from PySide6.QtCore import QSettings, QThreadPool
    from PySide6.QtWidgets import QApplication
    from pr7p import theme
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    from pr7p.main_window import apply_look
    apply_look(app)
    yield app
    QThreadPool.globalInstance().waitForDone(15000)
    for w in app.topLevelWidgets():
        w.close()
    app.clipboard().clear()
    app.processEvents()


@pytest.fixture(autouse=True)
def own_trash(tmp_path, monkeypatch):
    monkeypatch.setenv("PR7P_TRASH", str(tmp_path / "_trash"))
    yield tmp_path / "_trash"


@pytest.fixture
def clean_settings(qapp):
    from PySide6.QtCore import QSettings
    s = QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, "Paragon", "PR7-P")
    s.clear(); s.sync()
    yield
    s.clear(); s.sync()


@pytest.fixture
def pictures(qapp, tmp_path):
    """A folder of 8 real pictures (one upright, one PNG), the second with camera details."""
    import sample_images
    files = sample_images.folder(tmp_path / "Pictures", 8, (600, 400))
    sample_images.with_exif(files[1])
    return files


@pytest.fixture
def window(qapp, clean_settings):
    from pr7p.main_window import MainWindow
    w = MainWindow(thumbs_sync=True)
    # An error box nobody answers would wait forever: fail the test with its text instead.
    w.answers["error"] = lambda text: pytest.fail(f"PR7-P showed an error: {text}")
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    yield w
    w.modified = False
    w.close()
    w.deleteLater()
    qapp.processEvents()
