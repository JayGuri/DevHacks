# QUICKSTART_MONGODB.md - Fast Setup Guide

# MongoDB Atlas Integration - 5 Minute Quickstart

## Prerequisites
- ✅ MongoDB Atlas account (you already have this!)
- ✅ Connection string in `.env` (already configured)

---

## Step 1: Install Dependencies (30 seconds)

```powershell
cd C:\Users\naikb\OneDrive\Desktop\Projects\DevHacksCSIACE\DevHacks
pip install motor beanie pymongo
```

---

## Step 2: Test Connection (10 seconds)

```powershell
python test_mongodb_connection.py
```

**Expected output:**
```
======================================================================
MongoDB Atlas Connection Test
======================================================================

📋 Step 1: Checking environment variables...
✅ MONGODB_URL found
✅ DATABASE_NAME: arfl_platform

🔌 Step 2: Testing MongoDB connection...
✅ MongoDB connection successful!
✅ MongoDB version: 7.0.x
✅ Accessible databases: ['admin', 'arfl_platform']

⚡ Step 3: Testing Motor (async driver)...
✅ Motor async connection successful!

📦 Step 4: Testing Beanie (ODM)...
✅ Beanie version: 1.24.0

======================================================================
🎉 All tests passed! MongoDB Atlas is ready.
======================================================================
```

---

## Step 3: Start MongoDB Backend (5 seconds)

```powershell
cd backend
python app_mongo.py
```

**Server runs at:** http://localhost:8000

---

## Step 4: Test API (1 minute)

### Open new terminal and test:

```powershell
# Health check
curl http://localhost:8000/health

# Create user
curl -X POST http://localhost:8000/api/auth/signup `
  -H "Content-Type: application/json" `
  -d '{\"name\":\"Alice\",\"email\":\"alice@test.com\",\"password\":\"pass123\"}'

# Login (copy the token from response)
curl -X POST http://localhost:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"alice@test.com\",\"password\":\"pass123\"}'
```

---

## Step 5: View Data in MongoDB Atlas (1 minute)

1. Go to: https://cloud.mongodb.com
2. Login
3. Click "Browse Collections"
4. Select `arfl_platform` database
5. See your data in `users` collection!

---

## 🎯 Done! Your MongoDB cloud integration is live.

### What you now have:
- ✅ Cloud database (not local SQLite)
- ✅ Async operations (fast!)
- ✅ Scalable (512MB → 4TB+)
- ✅ Automatic backups
- ✅ Production-ready

### Architecture:
```
[Frontend] → [Backend API] → [MongoDB Atlas Cloud]
              localhost:8000   cluster0.ovvgemi.mongodb.net
```

---

## 🚀 Running Both Backends (Side-by-Side)

### Terminal 1: SQLite Backend (old)
```powershell
cd backend
python app.py  # Runs on port 8000
```

### Terminal 2: MongoDB Backend (new)
```powershell
cd backend
$env:PORT="8001"
python app_mongo.py  # Runs on port 8001
```

### Compare performance:
- SQLite: http://localhost:8000/health
- MongoDB: http://localhost:8001/health

---

## 📊 Key Differences

| Feature | SQLite (app.py) | MongoDB (app_mongo.py) |
|---------|----------------|------------------------|
| Database | Local file | Cloud cluster |
| Scalability | ~1GB | 512MB → 4TB+ |
| Backups | Manual | Automatic |
| Concurrent writes | Locked | Multi-writer |
| Location | Same PC | Cloud (global) |

---

## 🎥 For Demo Recording

1. Show `test_mongodb_connection.py` passing all tests
2. Show MongoDB Atlas dashboard with live data
3. Create user via API → immediately visible in Atlas
4. Create project → show in Atlas collections
5. Refresh Atlas → data updates in real-time
6. Highlight "Cloud-Native Architecture"

---

## 📞 Need Help?

**Connection issues?**
- MongoDB Atlas → Security → Network Access
- Add IP: 0.0.0.0/0 (allow all)

**Module not found?**
```powershell
pip install motor beanie pymongo
```

**Port already in use?**
```powershell
$env:PORT="8001"
python app_mongo.py
```

---

## ✅ Success Criteria

- [ ] `test_mongodb_connection.py` passes all 4 tests
- [ ] Backend starts without errors
- [ ] `/health` endpoint shows MongoDB connected
- [ ] User signup creates entry in Atlas
- [ ] Data visible in MongoDB Atlas dashboard
- [ ] Frontend can connect (same API, different backend)

**ALL GREEN? You're ready for demo! 🎉**
