# AWS Deployment Script for Soccer Predictions App
# Run this step by step - don't run the whole script at once!

# Variables - CHANGE THESE TO YOUR VALUES
$BUCKET_NAME = "soccer-predictions-app-$(Get-Random)"
$REGION = "us-east-1"
$DOMAIN = "yourdomain.com"

Write-Host "🚀 Deploying Soccer Predictions App to AWS..." -ForegroundColor Green

# Step 1: Create S3 bucket
Write-Host "📦 Creating S3 bucket: $BUCKET_NAME" -ForegroundColor Yellow
aws s3 mb s3://$BUCKET_NAME --region $REGION

# Step 2: Enable static website hosting
Write-Host "🌐 Configuring static website hosting..." -ForegroundColor Yellow
aws s3 website s3://$BUCKET_NAME --index-document index.html --error-document index.html

# Step 3: Set bucket policy for public read
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

# Step 4: Build and upload
Write-Host "🔨 Building application..." -ForegroundColor Yellow
Set-Location frontend
npm run build

Write-Host "📤 Uploading to S3..." -ForegroundColor Yellow
aws s3 sync dist/ s3://$BUCKET_NAME --delete
Set-Location ..

Write-Host "✅ Basic deployment complete!" -ForegroundColor Green
Write-Host "📍 S3 Website URL: http://$BUCKET_NAME.s3-website-$REGION.amazonaws.com" -ForegroundColor Cyan

# Cleanup
Remove-Item bucket-policy.json -ErrorAction SilentlyContinue

Write-Host "💡 Your app is now live! Test the S3 URL above." -ForegroundColor Green
Write-Host "💡 Next: Run deploy-cloudfront.ps1 to add CDN and custom domain" -ForegroundColor Yellow
