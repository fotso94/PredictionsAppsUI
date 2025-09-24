# AWS Deployment Script for Soccer Predictions App
# PowerShell version for Windows

# Variables - CHANGE THESE TO YOUR VALUES
$BUCKET_NAME = "soccer-predictions-app-$(Get-Random -Minimum 1000 -Maximum 9999)"
$REGION = "us-east-1"

Write-Host "🚀 Deploying Soccer Predictions App to AWS..." -ForegroundColor Green
Write-Host "📦 Bucket name will be: $BUCKET_NAME" -ForegroundColor Cyan

# Check if AWS CLI is configured
Write-Host "🔍 Checking AWS configuration..." -ForegroundColor Yellow
try {
    $awsIdentity = aws sts get-caller-identity 2>$null | ConvertFrom-Json
    Write-Host "✅ AWS configured for user: $($awsIdentity.Arn)" -ForegroundColor Green
} catch {
    Write-Host "❌ AWS CLI not configured. Please run: aws configure" -ForegroundColor Red
    Write-Host "You need:" -ForegroundColor Yellow
    Write-Host "  - AWS Access Key ID" -ForegroundColor Yellow
    Write-Host "  - AWS Secret Access Key" -ForegroundColor Yellow
    Write-Host "  - Default region: us-east-1" -ForegroundColor Yellow
    Write-Host "  - Default output format: json" -ForegroundColor Yellow
    exit 1
}

# Step 1: Build the application
Write-Host "🔨 Building application..." -ForegroundColor Yellow
if (Test-Path "frontend") {
    Set-Location frontend
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Build failed!" -ForegroundColor Red
        exit 1
    }
    Set-Location ..
} else {
    Write-Host "❌ Frontend directory not found!" -ForegroundColor Red
    exit 1
}

# Step 2: Create S3 bucket
Write-Host "📦 Creating S3 bucket: $BUCKET_NAME" -ForegroundColor Yellow
aws s3 mb s3://$BUCKET_NAME --region $REGION
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to create bucket. It might already exist." -ForegroundColor Red
    # Try a different name
    $BUCKET_NAME = "soccer-predictions-app-$(Get-Random -Minimum 10000 -Maximum 99999)"
    Write-Host "🔄 Trying with: $BUCKET_NAME" -ForegroundColor Yellow
    aws s3 mb s3://$BUCKET_NAME --region $REGION
}

# Step 3: Enable static website hosting
Write-Host "🌐 Configuring static website hosting..." -ForegroundColor Yellow
aws s3 website s3://$BUCKET_NAME --index-document index.html --error-document index.html

# Step 4: Set bucket policy for public read
Write-Host "🔓 Setting bucket policy..." -ForegroundColor Yellow
$bucketPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$BUCKET_NAME/*"
        }
    ]
}
"@

$bucketPolicy | Out-File -FilePath "bucket-policy.json" -Encoding UTF8
aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file://bucket-policy.json

# Step 5: Upload files
Write-Host "📤 Uploading files to S3..." -ForegroundColor Yellow
aws s3 sync frontend/dist/ s3://$BUCKET_NAME --delete

# Step 6: Get website URL
$WEBSITE_URL = "http://$BUCKET_NAME.s3-website-$REGION.amazonaws.com"

Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host "📍 Your app is live at: $WEBSITE_URL" -ForegroundColor Cyan
Write-Host "🌍 Bucket name: $BUCKET_NAME" -ForegroundColor Cyan

# Save deployment info
$deploymentInfo = @"
Deployment Information
=====================
Bucket Name: $BUCKET_NAME
Region: $REGION
Website URL: $WEBSITE_URL
Deployed: $(Get-Date)

Next Steps:
1. Test your app at the URL above
2. (Optional) Set up CloudFront for custom domain and HTTPS
3. (Optional) Configure your custom domain DNS

Cost Estimate: ~$1-3/month
"@

$deploymentInfo | Out-File -FilePath "deployment-info.txt" -Encoding UTF8

# Cleanup
Remove-Item bucket-policy.json -ErrorAction SilentlyContinue

Write-Host "💾 Deployment info saved to: deployment-info.txt" -ForegroundColor Green
Write-Host "💡 Test your app now: $WEBSITE_URL" -ForegroundColor Yellow

# Ask if user wants to open the URL
$openBrowser = Read-Host "🌐 Open the website in browser? (y/n)"
if ($openBrowser -eq 'y' -or $openBrowser -eq 'Y') {
    Start-Process $WEBSITE_URL
}
