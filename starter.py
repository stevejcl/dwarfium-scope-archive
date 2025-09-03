#! /usr/bin/python3

import os
import sys
import subprocess

def info():
	message = '''    Startup Script for Dwarfium Scope Archive for Linux and macOS
    (c) 2025, Stefan Schmidt-Bilkenroth'''
	print(message)

def start_inside_venv(venvpath, thescript):
	venvpython = os.sep.join([venvpath, "bin", "python"])
	if sys.prefix == sys.base_prefix:
		print( "    ... not running in a virtual environment")
		if not os.path.exists(os.sep.join([venvpath, "bin", "python"])):
			print( "    ... no virtual environment found - create new one at {}".format(venvpath))
			subprocess.check_call([sys.executable, "-m", "venv", venvpath])
			subprocess.check_call([venvpython, "-m", "pip", "install", "-r", "requirements.txt"])
		print( "    ... restarting inside the virtual environment")
		p=subprocess.Popen([venvpython, "./starter.py", "-s"])
		p.wait()
		exit(0)
	else:
		print( "    ... starting {} from virtual environment\n".format(thescript))
		p=subprocess.Popen([venvpython, thescript])
		p.wait()
		print( "    ... {} ended with status {}".format(thescript, p.returncode))

def main():
	if len(sys.argv) < 2:
		info()
	venvpath = os.sep.join([".", "venv"])
	start_inside_venv(venvpath, "dwarfium_scope_archive.py")

if __name__ == "__main__":
	main()