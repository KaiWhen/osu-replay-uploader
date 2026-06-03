from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi
from src.config import MONGO_URI

mongo_client = AsyncMongoClient(MONGO_URI, server_api=ServerApi('1'))

db = mongo_client['replaybotdb']
