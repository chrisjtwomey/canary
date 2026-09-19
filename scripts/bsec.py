"""Link Bosch's BSEC2 binary without building its Arduino wrapper.

The bsec2 package's own sources need Bosch's BME68x Arduino library, which
brings a second copy of the BME68x API that lib/bme68x already provides. So
platformio.ini installs the package and keeps it out of the build with
lib_ignore, and this script adds only its headers, its configuration blobs
and the precompiled libalgobsec for the ESP32.
"""
import os

Import("env")  # noqa: F821 - injected by PlatformIO

root = os.path.join(env.subst("$PROJECT_LIBDEPS_DIR"), env.subst("$PIOENV"), "bsec2")  # noqa: F821
# Bosch ships one binary per core. The head is an ESP32, the dock an ESP32-S3.
mcu = env.BoardConfig().get("build.mcu")  # noqa: F821
binary = os.path.join(root, "src", mcu)
if not os.path.isdir(binary):
    print(f"BSEC2 has no binary for {mcu} at {binary}; lib_deps in platformio.ini names the package")
    env.Exit(1)  # noqa: F821

env.Append(  # noqa: F821
    CPPPATH=[os.path.join(root, "src", "inc"), os.path.join(root, "src", "config")],
    LIBPATH=[binary],
    LIBS=["algobsec"],
)
