import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access environment variables
MONGO_CLOUD_URI = os.getenv('MONGO_CLOUD_URI')
