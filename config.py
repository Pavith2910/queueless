import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file into environment variables


class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "queueless")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    STAFF_PIN = os.getenv("STAFF_PIN", "1234")
    DEMO_TIME = os.getenv("DEMO_TIME", "")   # e.g. "13:00" to pretend it's 1 PM