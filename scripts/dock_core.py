"""Stop a dock build in the default PlatformIO folder, before it changes it.

The dock's custom_sdkconfig makes pioarduino compile the IDF libraries again,
into the framework package that every build in the folder shares. The
display's build then asks for a reinstall and fails. Runs before the
platform's own build script, which is where that compile happens.
"""
import os

Import("env")  # noqa: F821 - injected by PlatformIO

core = os.path.realpath(env.subst("$PROJECT_CORE_DIR"))  # noqa: F821
if core == os.path.realpath(os.path.expanduser("~/.platformio")):
    print("Dock build stopped: ~/.platformio is shared with the display. Build the dock in its own folder:")
    print(f"  PLATFORMIO_CORE_DIR=~/.platformio-canary-dock pio run -e {env.subst('$PIOENV')}")  # noqa: F821
    env.Exit(1)  # noqa: F821
