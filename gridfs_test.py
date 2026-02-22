import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test")

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import gridfs
import io
import torch

def test_gridfs():
    uri = "mongodb+srv://sakshat193_db_user:tu6Z1c1VqVGBr90u@cluster0.ovvgemi.mongodb.net/?appName=Cluster0"
    logger.info("Connecting...")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000, server_api=ServerApi('1'))
    db = client["fedbuff_db"]
    fs = gridfs.GridFS(db)
    
    logger.info("Finding partition 0...")
    grid_file = fs.find_one({"metadata.partition_id": 0})
    if not grid_file:
        logger.error("Partition 0 not found!")
        return
        
    logger.info("Found file. Reading data...")
    raw_data = grid_file.read()
    logger.info(f"Read {len(raw_data)} bytes. Deserializing...")
    
    buffer = io.BytesIO(raw_data)
    partition = torch.load(buffer, map_location="cpu", weights_only=False)
    logger.info("Done!")

if __name__ == "__main__":
    test_gridfs()
