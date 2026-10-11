from pathlib import Path
from types import SimpleNamespace

from desktop import autostart


class _Key:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, *_args):
        if autostart.AUTOSTART_REG_NAME not in self.values:
            raise FileNotFoundError
        return _Key()

    def CreateKeyEx(self, *_args):
        return _Key()

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], self.REG_SZ

    def SetValueEx(self, _key, name, _reserved, _kind, value):
        self.values[name] = value

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_build_autostart_command_uses_module_entrypoint(monkeypatch, tmp_path):
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.touch()
    pythonw.touch()
    monkeypatch.setattr(autostart.sys, "executable", str(python))
    monkeypatch.setattr(autostart.sys, "frozen", False, raising=False)

    command = autostart.build_autostart_command()

    assert str(pythonw.resolve()) in command
    assert "run_module('desktop.app',run_name='__main__')" in command
    project_root = str(Path(autostart.__file__).resolve().parent.parent)
    assert project_root.replace("\\", "\\\\") in command


def test_autostart_manager_can_enable_and_disable(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(autostart, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(autostart, "winreg", fake)
    manager = autostart.AutostartManager(command='"C:\\GoActivity.exe"')

    assert manager.is_enabled() is False

    manager.set_enabled(True)
    assert manager.is_enabled() is True
    assert fake.values[autostart.AUTOSTART_REG_NAME] == '"C:\\GoActivity.exe"'

    manager.set_enabled(False)
    assert manager.is_enabled() is False


def test_disabling_missing_autostart_entry_is_idempotent(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(autostart, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(autostart, "winreg", fake)

    autostart.AutostartManager().set_enabled(False)
