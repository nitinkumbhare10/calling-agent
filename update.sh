#!/bin/bash
# VPS Side automated code update & PM2 reload script
echo "================================================="
echo "🔄 Starting Outbound Agent Update & Deployment..."
echo "================================================="

# 1. Target Directories
TARGET_DIR="/home/devcloud/calling-agent"
ZIP_URL="https://filebin.net/callingagent-88716/calling-agent.zip"
TEMP_ZIP="/home/devcloud/calling-agent.zip"

# 2. Download the uploaded zip from Filebin
echo "📥 Downloading updated zip from filebin..."
wget -q -O "$TEMP_ZIP" "$ZIP_URL"

if [ $? -eq 0 ]; then
    echo "✅ Download successful!"
else
    echo "❌ Download failed! Make sure zip_and_upload.ps1 has finished running on your laptop."
    exit 1
fi

# 3. Extract the files and overwrite existing ones
echo "📂 Unzipping and updating server files..."
unzip -o "$TEMP_ZIP" -d "$TARGET_DIR"

# Clean up the temp zip
rm "$TEMP_ZIP"

# 4. Make update.sh executable on the server
chmod +x "$TARGET_DIR/update.sh"

# 5. Reload the Python Calling Agent in PM2
echo "🐍 Reloading Python Calling Agent in PM2..."
pm2 reload calling-agent

# 6. Rebuild Next.js Dashboard & reload PM2
echo "💻 Rebuilding Next.js Dashboard production bundle..."
cd "$TARGET_DIR/dashboard"
npm run build

echo "🌐 Reloading Next.js Dashboard in PM2..."
pm2 reload dashboard

echo "================================================="
echo "✅ Deployment completed successfully! Current status:"
echo "================================================="
pm2 status
