"""Entry point stored inside the Windows executable."""

import sys


def main():
    """Open the same desktop app as the source version. If Windows has Python
    but Tk or the GUI fails to start, show a readable error in a window.
    """
    try:
        from app import SupportSnap
        SupportSnap().mainloop()
    except Exception as error:
        if sys.platform != "win32":
            raise
        from ctypes import windll
        windll.user32.MessageBoxW(0, f"SupportSnap could not open.\n\n{error}\n\nCheck that Python has Tcl/Tk installed.",
                                  "SupportSnap", 16)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
