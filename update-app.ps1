# Quick Update Script - Deploy changes to existing AWS setup

Write-Host "🔄 Updating Soccer Predictions App..." -ForegroundColor Green

# Read deployment info
if (-not (Test-Path "deployment-info.txt")) {
    Write-Host "❌ deployment-info.txt not found. Run deploy-aws.ps1 first!" -ForegroundColor Red
    exit 1
}

$deployInfo = Get-Content "deployment-info.txt" -Raw
$BucketName = ""
$DistributionId = ""

if ($deployInfo -match "Bucket Name: (.+)") {
    $BucketName = $matches[1].Trim()
}

if ($deployInfo -match "CloudFront Distribution ID: (.+)") {
    $DistributionId = $matches[1].Trim()
}

if (-not $BucketName) {
    Write-Host "❌ Could not find bucket name in deployment info!" -ForegroundColor Red
    exit 1
}

Write-Host "📦 Updating bucket: $BucketName" -ForegroundColor Cyan

# Build the application
Write-Host "🔨 Building application..." -ForegroundColor Yellow
Set-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}
Set-Location ..

# Upload to S3
Write-Host "📤 Uploading to S3..." -ForegroundColor Yellow
aws s3 sync frontend/dist/ s3://$BucketName --delete

# Invalidate CloudFront cache if distribution exists
if ($DistributionId) {
    Write-Host "🔄 Invalidating CloudFront cache..." -ForegroundColor Yellow
    aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*"
    Write-Host "✅ Cache invalidation started (takes 1-2 minutes)" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No CloudFront distribution found - S3 only deployment" -ForegroundColor Yellow
}

Write-Host "✅ Update complete!" -ForegroundColor Green
Write-Host "🌍 Your changes are live!" -ForegroundColor Cyan

# Show URLs
$S3_URL = "http://$BucketName.s3-website-us-east-1.amazonaws.com"
Write-Host "📍 S3 URL: $S3_URL" -ForegroundColor Cyan

if ($deployInfo -match "CloudFront URL: (.+)") {
    $CloudFrontURL = $matches[1].Trim()
    Write-Host "🌍 CloudFront URL: $CloudFrontURL" -ForegroundColor Cyan
    Write-Host "⏱️  CloudFront cache will update in 1-2 minutes" -ForegroundColor Yellow
}
