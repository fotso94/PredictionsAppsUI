# 🚀 AWS Setup Guide for Soccer Predictions App

## Step 1: Get AWS Credentials

### 1.1 Create AWS Account
1. Go to [aws.amazon.com](https://aws.amazon.com)
2. Click **Create an AWS Account**
3. Complete registration (credit card required for verification)
4. Verify your email and phone number

### 1.2 Create Access Keys
1. **Login to AWS Console**: [console.aws.amazon.com](https://console.aws.amazon.com)
2. **Click your name** in top-right corner
3. **Select "Security credentials"**
4. **Scroll to "Access keys"** section
5. **Click "Create access key"**
6. **Choose "Command Line Interface (CLI)"**
7. **Check the confirmation box**
8. **Click "Next"**
9. **Add description**: "Soccer Predictions Deployment"
10. **Click "Create access key"**
11. **IMPORTANT**: Download the CSV file or copy both keys:
    - Access Key ID (starts with AKIA...)
    - Secret Access Key (long random string)

## Step 2: Configure AWS CLI

### 2.1 Run Configuration Command
```powershell
aws configure
```

### 2.2 Enter Your Information
When prompted, enter:
```
AWS Access Key ID [None]: AKIA... (your access key)
AWS Secret Access Key [None]: ... (your secret key)
Default region name [None]: us-east-1
Default output format [None]: json
```

### 2.3 Test Configuration
```powershell
aws sts get-caller-identity
```

You should see your account information.

## Step 3: Deploy Your App

### 3.1 Run Deployment Script
```powershell
powershell -ExecutionPolicy Bypass -File deploy-aws.ps1
```

### 3.2 What the Script Does
1. ✅ Builds your React app (`npm run build`)
2. ✅ Creates a unique S3 bucket
3. ✅ Configures bucket for static website hosting
4. ✅ Sets public read permissions
5. ✅ Uploads your app files
6. ✅ Provides you with the live URL

### 3.3 Expected Output
```
🚀 Deploying Soccer Predictions App to AWS...
📦 Bucket name will be: soccer-predictions-app-1234
✅ AWS configured for user: arn:aws:iam::123456789:user/yourname
🔨 Building application...
📦 Creating S3 bucket: soccer-predictions-app-1234
🌐 Configuring static website hosting...
🔓 Setting bucket policy...
📤 Uploading files to S3...
✅ Deployment complete!
📍 Your app is live at: http://soccer-predictions-app-1234.s3-website-us-east-1.amazonaws.com
```

## Step 4: (Optional) Add CloudFront CDN

### 4.1 Run CloudFront Setup
```powershell
powershell -ExecutionPolicy Bypass -File setup-cloudfront.ps1 -BucketName "your-bucket-name"
```

### 4.2 Benefits of CloudFront
- ✅ HTTPS support (SSL certificate)
- ✅ Global CDN (faster loading worldwide)
- ✅ Custom domain support
- ✅ Better caching

## Step 5: Connect Your Custom Domain

### 5.1 Get CloudFront Domain
After CloudFront deploys (10-15 minutes), you'll get a domain like:
`d1234567890.cloudfront.net`

### 5.2 Update Namecheap DNS
1. **Login to Namecheap**
2. **Go to Domain List** → **Manage** your domain
3. **Advanced DNS** tab
4. **Add/Update records**:
   ```
   Type: CNAME
   Host: @
   Value: d1234567890.cloudfront.net
   TTL: Automatic
   
   Type: CNAME  
   Host: www
   Value: d1234567890.cloudfront.net
   TTL: Automatic
   ```

## 💰 Cost Breakdown

### Free Tier (First 12 months)
- **S3**: 5GB storage, 20,000 GET requests, 2,000 PUT requests
- **CloudFront**: 50GB data transfer, 2,000,000 requests
- **Route 53**: $0.50/month per hosted zone (if using custom domain)

### After Free Tier
- **S3**: ~$0.50/month (your app is ~10MB)
- **CloudFront**: ~$1-2/month (depends on traffic)
- **Total**: ~$1-3/month

## 🔄 Future Updates

### Update Your App
```powershell
powershell -ExecutionPolicy Bypass -File update-app.ps1
```

This will:
1. Build your latest changes
2. Upload to S3
3. Invalidate CloudFront cache
4. Your changes go live in 1-2 minutes

## 🆘 Troubleshooting

### "InvalidAccessKeyId" Error
- Double-check your access key and secret key
- Make sure you copied them correctly (no extra spaces)
- Try creating new access keys

### "Bucket already exists" Error
- S3 bucket names are globally unique
- The script will try different names automatically
- Or manually change the bucket name in the script

### Build Fails
- Make sure you're in the project root directory
- Run `cd frontend && npm install` first
- Check that `frontend/dist` folder exists after build

### Need Help?
- Check AWS CloudTrail for detailed error logs
- AWS Support (free tier includes basic support)
- AWS Documentation: [docs.aws.amazon.com](https://docs.aws.amazon.com)
