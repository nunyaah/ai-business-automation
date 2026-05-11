import sys
import os

# Make `src` importable when running pytest from invoice-agent/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
