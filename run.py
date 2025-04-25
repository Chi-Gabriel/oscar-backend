# File: run.py

from kapricorn import create_app
import os

# Load environment variables from .env file if it exists
# This is helpful if run.py is executed directly without activating env first in some scenarios
from dotenv import load_dotenv
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = create_app()

if __name__ == '__main__':
    # Set debug=True for development, but False for production!
    app.run(host='0.0.0.0', port=5000, debug=True)