# CloudFront Setup for Custom Domain and HTTPS
# Run this AFTER deploy-aws.ps1

param(
    [Parameter(Mandatory=$true)]
    [string]$BucketName,
    
    [Parameter(Mandatory=$false)]
    [string]$CustomDomain = ""
)

Write-Host "🌍 Setting up CloudFront CDN..." -ForegroundColor Green

# Read deployment info if available
if (Test-Path "deployment-info.txt") {
    $deployInfo = Get-Content "deployment-info.txt" -Raw
    if ($deployInfo -match "Bucket Name: (.+)") {
        $BucketName = $matches[1].Trim()
        Write-Host "📖 Found bucket name: $BucketName" -ForegroundColor Cyan
    }
}

if (-not $BucketName) {
    $BucketName = Read-Host "Enter your S3 bucket name"
}

$REGION = "us-east-1"
$S3_WEBSITE_ENDPOINT = "$BucketName.s3-website-$REGION.amazonaws.com"

Write-Host "🔧 Creating CloudFront distribution..." -ForegroundColor Yellow
Write-Host "📍 Origin: $S3_WEBSITE_ENDPOINT" -ForegroundColor Cyan

# Create CloudFront distribution config
$cloudfrontConfig = @"
{
    "CallerReference": "soccer-predictions-$(Get-Date -Format 'yyyyMMddHHmmss')",
    "Comment": "Soccer Predictions App CDN",
    "DefaultRootObject": "index.html",
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "S3-$BucketName",
                "DomainName": "$S3_WEBSITE_ENDPOINT",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only"
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "S3-$BucketName",
        "ViewerProtocolPolicy": "redirect-to-https",
        "TrustedSigners": {
            "Enabled": false,
            "Quantity": 0
        },
        "ForwardedValues": {
            "QueryString": false,
            "Cookies": {
                "Forward": "none"
            }
        },
        "MinTTL": 0,
        "Compress": true
    },
    "CustomErrorResponses": {
        "Quantity": 1,
        "Items": [
            {
                "ErrorCode": 404,
                "ResponsePagePath": "/index.html",
                "ResponseCode": "200",
                "ErrorCachingMinTTL": 300
            }
        ]
    },
    "Enabled": true,
    "PriceClass": "PriceClass_100"
}
"@

$cloudfrontConfig | Out-File -FilePath "cloudfront-config.json" -Encoding UTF8

Write-Host "🚀 Creating CloudFront distribution (this takes 10-15 minutes)..." -ForegroundColor Yellow
$distributionResult = aws cloudfront create-distribution --distribution-config file://cloudfront-config.json | ConvertFrom-Json

$DISTRIBUTION_ID = $distributionResult.Distribution.Id
$CLOUDFRONT_DOMAIN = $distributionResult.Distribution.DomainName

Write-Host "✅ CloudFront distribution created!" -ForegroundColor Green
Write-Host "🆔 Distribution ID: $DISTRIBUTION_ID" -ForegroundColor Cyan
Write-Host "🌍 CloudFront URL: https://$CLOUDFRONT_DOMAIN" -ForegroundColor Cyan
Write-Host "⏱️  Status: Deploying (10-15 minutes)" -ForegroundColor Yellow

# Update deployment info
$updatedInfo = @"
Deployment Information
=====================
Bucket Name: $BucketName
Region: $REGION
S3 Website URL: http://$S3_WEBSITE_ENDPOINT
CloudFront Distribution ID: $DISTRIBUTION_ID
CloudFront URL: https://$CLOUDFRONT_DOMAIN
Deployed: $(Get-Date)

Status: CloudFront is deploying (10-15 minutes)

Custom Domain Setup:
1. Wait for CloudFront to deploy
2. In your domain registrar (Namecheap), create:
   - A record: @ -> $CLOUDFRONT_DOMAIN (or use ALIAS if supported)
   - CNAME record: www -> $CLOUDFRONT_DOMAIN

Cost Estimate: ~$1-3/month
"@

$updatedInfo | Out-File -FilePath "deployment-info.txt" -Encoding UTF8

# Cleanup
Remove-Item cloudfront-config.json -ErrorAction SilentlyContinue

Write-Host "💾 Updated deployment info saved" -ForegroundColor Green
Write-Host ""
Write-Host "🎯 Next Steps:" -ForegroundColor Yellow
Write-Host "1. ⏱️  Wait 10-15 minutes for CloudFront deployment" -ForegroundColor White
Write-Host "2. 🧪 Test: https://$CLOUDFRONT_DOMAIN" -ForegroundColor White
Write-Host "3. 🌐 (Optional) Set up custom domain in Namecheap DNS" -ForegroundColor White
Write-Host ""
Write-Host "📊 Check deployment status:" -ForegroundColor Yellow
Write-Host "aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status'" -ForegroundColor Gray

# Function to check status
Write-Host "🔍 Checking current status..." -ForegroundColor Yellow
$status = aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status' --output text
Write-Host "📊 Current status: $status" -ForegroundColor Cyan

if ($status -eq "Deployed") {
    Write-Host "🎉 CloudFront is ready! Your app is live at: https://$CLOUDFRONT_DOMAIN" -ForegroundColor Green
} else {
    Write-Host "⏳ Still deploying... Check again in a few minutes" -ForegroundColor Yellow
}
