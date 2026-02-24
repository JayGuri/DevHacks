# run_mongodb_setup.ps1 - Automated MongoDB Setup Script
# Run this script to complete MongoDB integration in one command

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MongoDB Atlas Integration Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Python version
Write-Host "[1/5] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python not found. Please install Python 3.10+" -ForegroundColor Red
    exit 1
}

# Step 2: Install MongoDB packages
Write-Host ""
Write-Host "[2/5] Installing MongoDB packages..." -ForegroundColor Yellow
Write-Host "  Installing: motor, beanie, pymongo" -ForegroundColor Gray

pip install motor==3.3.2 beanie==1.24.0 pymongo==4.6.1 --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ MongoDB packages installed" -ForegroundColor Green
} else {
    Write-Host "  ✗ Installation failed. Check your internet connection" -ForegroundColor Red
    exit 1
}

# Step 3: Test MongoDB connection
Write-Host ""
Write-Host "[3/5] Testing MongoDB Atlas connection..." -ForegroundColor Yellow

python test_mongodb_connection.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ MongoDB connection successful" -ForegroundColor Green
} else {
    Write-Host "  ✗ Connection failed. Check your .env file" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Open .env and verify MONGODB_URL" -ForegroundColor Gray
    Write-Host "  2. MongoDB Atlas → Security → Network Access" -ForegroundColor Gray
    Write-Host "  3. Add IP: 0.0.0.0/0 (Allow all)" -ForegroundColor Gray
    exit 1
}

# Step 4: Check backend files
Write-Host ""
Write-Host "[4/5] Verifying backend files..." -ForegroundColor Yellow

$backendFiles = @(
    "backend\app_mongo.py",
    "backend\db\mongo_database.py",
    "backend\db\mongo_models.py",
    "backend\auth\routes_mongo.py"
)

$allFilesExist = $true
foreach ($file in $backendFiles) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file not found" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if (-not $allFilesExist) {
    Write-Host ""
    Write-Host "  Some files are missing. Please check the implementation." -ForegroundColor Red
    exit 1
}

# Step 5: Instructions to start
Write-Host ""
Write-Host "[5/5] Setup complete! 🎉" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Next Steps:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Start MongoDB Backend:" -ForegroundColor Yellow
Write-Host "   cd backend" -ForegroundColor Gray
Write-Host "   python app_mongo.py" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Open in browser:" -ForegroundColor Yellow
Write-Host "   http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Test API endpoints:" -ForegroundColor Yellow
Write-Host "   - Health check: http://localhost:8000/health" -ForegroundColor Gray
Write-Host "   - Signup: POST /api/auth/signup" -ForegroundColor Gray
Write-Host "   - Login: POST /api/auth/login" -ForegroundColor Gray
Write-Host ""
Write-Host "4. View data in MongoDB Atlas:" -ForegroundColor Yellow
Write-Host "   https://cloud.mongodb.com" -ForegroundColor Gray
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Offer to start backend automatically
Write-Host "Would you like to start the MongoDB backend now? (Y/N): " -ForegroundColor Yellow -NoNewline
$response = Read-Host

if ($response -eq "Y" -or $response -eq "y") {
    Write-Host ""
    Write-Host "Starting MongoDB backend..." -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
    Write-Host ""
    Set-Location backend
    python app_mongo.py
} else {
    Write-Host ""
    Write-Host "Setup complete! Run manually when ready." -ForegroundColor Green
    Write-Host ""
}
