import os

# config.py
DEBUG = os.environ.get('FLASK_DEBUG')
SERVER_NAME = os.environ.get("SERVER_NAME")
PORT = os.environ.get("SERVER_PORT")
SECRET_KEY = os.environ.get('SECRET_KEY') or '6KpbvdqgBEbJu3kG'

