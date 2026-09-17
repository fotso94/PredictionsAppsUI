# Expert UI Testing Guide

## 🚀 Servers Running

✅ **Backend**: http://localhost:8000
✅ **Frontend**: http://localhost:3000
✅ **Swagger UI**: http://localhost:8000/api/docs

---

## 🎯 Expert Dashboard Access

**URL**: http://localhost:3000/expert/dashboard

**Route**: `/expert/dashboard`

---

## 🧪 How to Test Expert UI

### **Step 1: Login as Expert User**

1. Go to: http://localhost:3000/login
2. Login with expert user credentials
3. You should be redirected to the dashboard

### **Step 2: Access Expert Dashboard**

**Option A - Direct URL:**
- Navigate to: http://localhost:3000/expert/dashboard

**Option B - Add Navigation Link (if needed):**
- You may need to add a link in the navigation menu
- For now, use the direct URL

### **Step 3: Test Expert Dashboard Features**

The Expert Dashboard should display:

#### **Performance Metrics Cards**
- 📊 Total Predictions
- ✅ Published Predictions
- ⏳ Pending Predictions
- 🎯 Accuracy Rate

#### **Quick Action Buttons**
- ➕ Create Prediction
- 📋 Review Queue
- 📝 My Predictions

#### **Recent Predictions List**
- Prediction cards with:
  - Source badge (👤 Expert, 🤖 LLM, ⭐ API-Football)
  - Status badge (Pending, Approved, Published)
  - Confidence badge (Low, Medium, High, Very High)
  - Probabilities (Home Win, Draw, Away Win)
  - Reasoning text
  - Creation date

#### **Review Queue Preview**
- List of pending predictions
- "View All" link

---

## 🔧 Testing Scenarios

### **Scenario 1: View Dashboard (Read-Only)**

1. Navigate to `/expert/dashboard`
2. Verify performance metrics load
3. Verify recent predictions display
4. Verify review queue shows pending items

**Expected Behavior:**
- ✅ Dashboard loads without errors
- ✅ API calls to backend successful
- ✅ Data displays correctly
- ✅ Source badges show correct icons and colors
- ✅ Status badges show correct colors

### **Scenario 2: Create Manual Prediction**

**Note**: The create prediction form is not yet implemented. The button links to `/expert/predictions/create` which needs to be created.

**For now, test via Swagger UI:**
1. Go to: http://localhost:8000/api/docs
2. Find: `POST /api/v1/expert/predictions/manual`
3. Click "Try it out"
4. Enter test data:
```json
{
  "match_id": "550e8400-e29b-41d4-a716-446655440000",
  "home_win_prob": 0.6,
  "draw_prob": 0.25,
  "away_win_prob": 0.15,
  "confidence_score": 0.85,
  "reasoning": "Home team has excellent form with 5 consecutive wins",
  "key_factors": {
    "home_form": "WWWWW"
  }
}
```
5. Click "Execute"
6. Refresh Expert Dashboard to see new prediction

### **Scenario 3: View Review Queue**

**Note**: The review queue page is not yet implemented. The button links to `/expert/predictions/review-queue` which needs to be created.

**For now, test via Swagger UI:**
1. Go to: http://localhost:8000/api/docs
2. Find: `GET /api/v1/expert/predictions/review-queue`
3. Click "Try it out"
4. Click "Execute"
5. Verify pending predictions are returned

### **Scenario 4: View My Predictions**

**Note**: The my predictions page is not yet implemented. The button links to `/expert/predictions/my-predictions` which needs to be created.

**For now, test via Swagger UI:**
1. Go to: http://localhost:8000/api/docs
2. Find: `GET /api/v1/expert/predictions/my-predictions`
3. Click "Try it out"
4. Click "Execute"
5. Verify your predictions are returned

---

## 🎨 UI Components Implemented

### **1. PredictionSourceBadge**
- ✅ Displays prediction source with icon
- ✅ Color-coded by source type
- ✅ Tooltip with description

### **2. PredictionPriorityBadge**
- ✅ Displays priority level (0-100)
- ✅ Color-coded by priority range

### **3. PredictionStatusBadge**
- ✅ Displays prediction status
- ✅ Color-coded by status (Pending, Approved, Published, etc.)

### **4. ConfidenceBadge**
- ✅ Displays confidence level
- ✅ Shows percentage
- ✅ Color-coded (Low, Medium, High, Very High)

### **5. ExpertDashboardPage**
- ✅ Performance metrics cards
- ✅ Quick action buttons
- ✅ Recent predictions list
- ✅ Review queue preview
- ✅ Loading states
- ✅ Error handling

---

## 🐛 Known Limitations

### **Pages Not Yet Implemented:**
1. ❌ `/expert/predictions/create` - Create prediction form
2. ❌ `/expert/predictions/review-queue` - Review queue page
3. ❌ `/expert/predictions/my-predictions` - My predictions page
4. ❌ `/expert/predictions/override` - Override prediction form

### **Navigation:**
- ❌ Expert Dashboard link not in main navigation menu
- ✅ Can access via direct URL: `/expert/dashboard`

### **Data:**
- ⚠️ Accuracy rate shows "N/A" (requires match outcome data)
- ⚠️ Predictions by league is empty (requires match metadata)
- ⚠️ Performance trend is empty (requires historical data)

---

## 🔐 Authentication Requirements

To access Expert Dashboard, you need:
1. ✅ Valid JWT token (logged in)
2. ✅ User role: `EXPERT` or `ADMIN`
3. ✅ Expert profile with `is_verified: true` (for creating/overriding predictions)

**If you get 403 Forbidden:**
- Check user has expert role
- Check expert is verified
- Check token is valid

---

## 📊 API Endpoints Used by Dashboard

The Expert Dashboard makes these API calls:

1. **GET /api/v1/expert/analytics/performance**
   - Loads performance metrics
   - Returns total predictions, accuracy, etc.

2. **GET /api/v1/expert/predictions/review-queue**
   - Loads pending predictions
   - Limited to 5 items for preview

**Check Network Tab:**
- Open browser DevTools (F12)
- Go to Network tab
- Refresh dashboard
- Verify API calls are successful (200 OK)

---

## 🎯 Testing Checklist

### **Visual Testing**
- [ ] Dashboard loads without errors
- [ ] Performance metrics display correctly
- [ ] Cards have proper styling
- [ ] Badges show correct colors and icons
- [ ] Responsive design works on mobile
- [ ] Dark mode works (if implemented)

### **Functional Testing**
- [ ] API calls succeed
- [ ] Data loads from backend
- [ ] Loading states show while fetching
- [ ] Error states show on API failure
- [ ] Retry button works on error
- [ ] Links navigate to correct routes

### **Data Testing**
- [ ] Metrics show correct numbers
- [ ] Recent predictions display
- [ ] Review queue shows pending items
- [ ] Probabilities sum to 100%
- [ ] Confidence scores display correctly
- [ ] Dates format correctly

---

## 🚀 Next Steps

### **To Complete Expert UI:**

1. **Create Prediction Form Page**
   - Route: `/expert/predictions/create`
   - Form with match selection, probabilities, reasoning
   - Validation for probabilities sum to 1.0
   - Submit to `POST /api/v1/expert/predictions/manual`

2. **Review Queue Page**
   - Route: `/expert/predictions/review-queue`
   - List of pending predictions
   - Pagination
   - Filter by status

3. **My Predictions Page**
   - Route: `/expert/predictions/my-predictions`
   - List of expert's predictions
   - Filter by status
   - Pagination

4. **Override Prediction Form**
   - Route: `/expert/predictions/override/:id`
   - Pre-fill with existing prediction
   - Form to update probabilities
   - Required reasoning field
   - Submit to `POST /api/v1/expert/predictions/override`

5. **Add Navigation Link**
   - Add "Expert Dashboard" link to main navigation
   - Show only for expert users
   - Highlight when active

---

## 📝 Quick Test Commands

### **Check Backend Health**
```bash
curl http://localhost:8000/api/v1/health
```

### **Check Frontend**
```bash
curl http://localhost:3000
```

### **Test Expert API (with auth token)**
```bash
# Get performance metrics
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/expert/analytics/performance

# Get review queue
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/expert/predictions/review-queue
```

---

## 🎉 Ready to Test!

**Open these URLs:**
1. Frontend: http://localhost:3000
2. Expert Dashboard: http://localhost:3000/expert/dashboard
3. Swagger UI: http://localhost:8000/api/docs

**Happy Testing! 🚀**

