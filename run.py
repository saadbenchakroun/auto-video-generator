"""
Auto Video Creator - Entry Point
Run this file to start the application.
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.ui import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
