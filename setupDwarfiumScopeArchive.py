from cx_Freeze import setup, Executable
import sys

# Include additional files and folders
buildOptions = dict(
)

# Define the base for a GUI application
base = 'Win32GUI' if sys.platform=='win32' else None
# Setup function
setup(
    name="Dwarfium Scope Archive",
    version="1.0",
    description="Dwarfium Scope Archive",
    options = dict(build_exe = buildOptions),
    executables=[Executable("dwarf_backup_cli.py")]
)
