"""
windows_setup.py

Configure PATH to access Thorlabs TSI SDK DLLs based on Python architecture.
"""

import os
import sys


def configure_path():
    """
    Add the correct DLL directory to PATH based on Python architecture (32-bit or 64-bit).
    Should be called before importing thorlabs_tsi_sdk modules.
    """
    is_64bits = sys.maxsize > 2 ** 32

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Choose the correct native library folder
    dll_folder = 'Native_64_lib' if is_64bits else 'Native_32_lib'
    dll_path = os.path.join(script_dir, dll_folder)

    # Add DLL directory to PATH
    if os.path.exists(dll_path):
        os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']

        # Python 3.8+ requires explicit DLL directory registration
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(dll_path)

        print(f"✓ Using {dll_folder} DLLs")
    else:
        raise FileNotFoundError(f"DLL directory not found: {dll_path}")
