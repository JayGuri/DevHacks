# test_mongodb_connection.py — Quick MongoDB Atlas connection test
"""
Run this to verify your MongoDB Atlas setup is correct.

Usage:
    python test_mongodb_connection.py
"""

import os
import sys
import asyncio
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

async def test_connection():
    """Test MongoDB Atlas connection."""
    print("\n" + "="*70)
    print("MongoDB Atlas Connection Test")
    print("="*70 + "\n")

    # Step 1: Check environment variables
    print("📋 Step 1: Checking environment variables...")
    mongodb_url = os.getenv("MONGODB_URL")
    database_name = os.getenv("DATABASE_NAME", "arfl_platform")
    
    if not mongodb_url:
        print("❌ ERROR: MONGODB_URL not found in .env file")
        print("   Add: MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/database")
        return False
    
    print(f"✅ MONGODB_URL found")
    print(f"✅ DATABASE_NAME: {database_name}")
    
    # Step 2: Test basic connection
    print("\n🔌 Step 2: Testing MongoDB connection...")
    try:
        from pymongo import MongoClient
        from pymongo.server_api import ServerApi
        
        # Create client with timeout
        client = MongoClient(
            mongodb_url,
            server_api=ServerApi('1'),
            serverSelectionTimeoutMS=5000
        )
        
        # Ping server
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        
        # Get server info
        server_info = client.server_info()
        print(f"✅ MongoDB version: {server_info['version']}")
        
        # List databases
        db_list = client.list_database_names()
        print(f"✅ Accessible databases: {db_list}")
        
        # Check if our database exists
        if database_name in db_list:
            print(f"✅ Database '{database_name}' exists")
            
            # List collections
            db = client[database_name]
            collections = db.list_collection_names()
            if collections:
                print(f"✅ Collections: {collections}")
            else:
                print(f"ℹ️  No collections yet (will be created on first use)")
        else:
            print(f"ℹ️  Database '{database_name}' will be created on first use")
        
        client.close()
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Check MongoDB Atlas → Security → Network Access")
        print("   2. Ensure IP address 0.0.0.0/0 is whitelisted")
        print("   3. Verify username/password in connection string")
        print("   4. Wait 1-2 minutes after making Atlas changes")
        return False
    
    # Step 3: Test Motor (async driver)
    print("\n⚡ Step 3: Testing Motor (async driver)...")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        
        async_client = AsyncIOMotorClient(mongodb_url)
        await async_client.admin.command('ping')
        print("✅ Motor async connection successful!")
        async_client.close()
        
    except ImportError:
        print("⚠️  Motor not installed. Run: pip install motor")
        print("   (Required for async operations)")
        return False
    except Exception as e:
        print(f"❌ Motor connection failed: {e}")
        return False
    
    # Step 4: Test Beanie (ODM)
    print("\n📦 Step 4: Testing Beanie (ODM)...")
    try:
        import beanie
        print(f"✅ Beanie version: {beanie.__version__}")
        
    except ImportError:
        print("⚠️  Beanie not installed. Run: pip install beanie")
        print("   (Required for document models)")
        return False
    
    # Success!
    print("\n" + "="*70)
    print("🎉 All tests passed! MongoDB Atlas is ready.")
    print("="*70)
    print("\n📝 Next steps:")
    print("   1. cd backend")
    print("   2. python app_mongo.py")
    print("   3. Open http://localhost:8000/docs")
    print("   4. Test API endpoints")
    print("\n")
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_connection())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
