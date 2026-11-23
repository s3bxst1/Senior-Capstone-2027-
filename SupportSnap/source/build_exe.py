"""Developer tool: make the same single Windows GUI launcher from the project source."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from pip._vendor import distlib


def build(folder, destination):
    """Pack the app, checks and sample data behind a Windows GUI launcher. The
    launcher starts the installed windowed Python interpreter and reads the
    archive in place; the user does not need source files beside the executable.
    """
    launcher = Path(distlib.__file__).with_name("w64.exe").read_bytes()
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for name in ("app.py", "ranking.py", "diagnostics.py", "live_checks.py", "on_device.py",
                     "test_diagnostics.py", "test_live_checks.py", "demo_cases.json", "windows_readings.ps1"):
            package.write(folder / name, name)
        package.write(folder / "start_gui.py", "__main__.py")
        package.writestr("DISTLIB-LICENSE.txt", Path(distlib.__file__).with_name("LICENSE.txt").read_bytes())
    destination.write_bytes(launcher + b"#!pyw.exe -3\n" + archive.getvalue())


if __name__ == "__main__":
    source = Path(__file__).resolve().parent
    build(source, source.parent / "SupportSnap.exe")
