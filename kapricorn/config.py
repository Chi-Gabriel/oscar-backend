import os
from dotenv import load_dotenv

# Load environment variables from .env file located in the parent directory
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Base configuration variables."""
    
    # API Keys from .env
    GOOGLE_API_KEY_FREE_CHAT = os.environ.get('GOOGLE_API_KEY_FREE_CHAT')
    GOOGLE_API_KEY_FREE_ACCESSORY = os.environ.get('GOOGLE_API_KEY_FREE_ACCESSORY')
    GOOGLE_API_KEY_PAID = os.environ.get('GOOGLE_API_KEY_PAID')
    GOOGLE_API_KEY_RECOMENDATIONS = os.environ.get('GOOGLE_API_KEY_RECOMENDATIONS')

    # Model Names from .env
    FREE_CHAT_MODEL_NAME = os.environ.get('FREE_CHAT_MODEL_NAME', 'gemini-1.0-pro')
    FREE_ACCESSORY_MODEL_NAME = os.environ.get('FREE_ACCESSORY_MODEL_NAME', 'gemini-1.0-pro')
    PAID_MODEL_NAME = os.environ.get('PAID_MODEL_NAME', 'gemini-1.5-flash')

   

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}