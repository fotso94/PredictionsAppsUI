# Expert Prediction Creation Form - User Guide

## Overview
This guide explains how to use the enhanced Expert Prediction Creation form with the new BTTS and Total Goals prediction fields.

**Form URL:** `http://localhost:3000/expert/predictions/create`

---

## Form Sections

### 1. Match ID (Required)
- **Field:** Text input
- **Description:** Enter the match ID for which you want to create a prediction
- **Example:** `1416498`
- **Note:** Can be pre-filled via URL parameter: `?matchId=1416498`

---

### 2. Match Outcome Probabilities (Required)
**Description:** Predict the 1X2 match outcome (Home Win / Draw / Away Win)

**Fields:**
- **Home Win:** Probability of home team winning (0-1)
- **Draw:** Probability of a draw (0-1)
- **Away Win:** Probability of away team winning (0-1)

**Validation:**
- All three probabilities must sum to **1.0** (100%)
- Each probability must be between 0 and 1
- Real-time total percentage display

**Example:**
```
Home Win: 0.45 (45%)
Draw: 0.30 (30%)
Away Win: 0.25 (25%)
Total: 100.0% ✅
```

---

### 3. Match Outcome Confidence (Optional)
- **Field:** Number input (0-1)
- **Description:** Your confidence level in the match outcome prediction
- **Default:** 0.75 (75%)
- **Example:** 0.80 = 80% confidence

---

### 4. Both Teams to Score (BTTS) - Optional ✨ NEW
**Description:** Predict whether both teams will score in the match

**Fields:**
- **Yes (Both Score):** Probability that both teams will score (0-1)
- **No (At Least One Won't Score):** Probability that at least one team won't score (0-1)
- **BTTS Confidence:** Your confidence level in this prediction (0-1)

**Validation:**
- If both Yes and No probabilities are provided, they must sum to **1.0** (100%)
- Warning message appears if sum ≠ 100%
- All fields are optional - you can skip this section entirely

**Example 1: Both teams likely to score**
```
Yes (Both Score): 0.65 (65%)
No (At Least One Won't Score): 0.35 (35%)
Total: 100.0% ✅
BTTS Confidence: 0.70 (70% confidence)
```

**Example 2: Defensive match**
```
Yes (Both Score): 0.40 (40%)
No (At Least One Won't Score): 0.60 (60%)
Total: 100.0% ✅
BTTS Confidence: 0.75 (75% confidence)
```

**Example 3: Skip this section**
```
Leave all fields empty - this is perfectly valid! ✅
```

---

### 5. Total Goals (Over/Under) - Optional ✨ NEW
**Description:** Predict the total number of goals in the match

**Fields:**
- **Over 2.5 Goals:** Probability of 3+ goals (0-1)
- **Under 2.5 Goals:** Probability of 0-2 goals (0-1)
- **Over 3.5 Goals:** Probability of 4+ goals (0-1)
- **Under 3.5 Goals:** Probability of 0-3 goals (0-1)
- **Total Goals Confidence:** Your confidence level in this prediction (0-1)

**Validation:**
- No strict sum validation (probabilities are independent)
- Each probability must be between 0 and 1
- All fields are optional - you can skip this section entirely

**Example 1: High-scoring match expected**
```
Over 2.5 Goals: 0.70 (70%)
Under 2.5 Goals: 0.30 (30%)
Over 3.5 Goals: 0.45 (45%)
Under 3.5 Goals: 0.55 (55%)
Total Goals Confidence: 0.75 (75% confidence)
```

**Example 2: Low-scoring match expected**
```
Over 2.5 Goals: 0.35 (35%)
Under 2.5 Goals: 0.65 (65%)
Over 3.5 Goals: 0.15 (15%)
Under 3.5 Goals: 0.85 (85%)
Total Goals Confidence: 0.80 (80% confidence)
```

**Example 3: Only predict Over/Under 2.5**
```
Over 2.5 Goals: 0.60 (60%)
Under 2.5 Goals: 0.40 (40%)
Over 3.5 Goals: (leave empty)
Under 3.5 Goals: (leave empty)
Total Goals Confidence: 0.70 (70% confidence)
```

**Example 4: Skip this section**
```
Leave all fields empty - this is perfectly valid! ✅
```

---

### 6. Reasoning (Optional)
- **Field:** Textarea
- **Description:** Explain your prediction reasoning
- **Max Length:** 2000 characters
- **Example:** "Home team has strong form, 5 wins in last 6 matches. Away team missing key striker."

---

### 7. Submit
- **Button:** "Create Prediction"
- **Action:** Submits the prediction for approval
- **Status:** Prediction will be in PENDING status until approved by admin
- **Redirect:** Automatically redirects to Expert Dashboard after 1.5 seconds

---

## Usage Scenarios

### Scenario 1: Complete Prediction (All Fields)
**Use Case:** You have strong insights on all aspects of the match

```
Match ID: 1416498
Home Win: 0.45, Draw: 0.30, Away Win: 0.25
Confidence: 0.85

BTTS Yes: 0.70, BTTS No: 0.30
BTTS Confidence: 0.75

Over 2.5: 0.65, Under 2.5: 0.35
Over 3.5: 0.40, Under 3.5: 0.60
Total Goals Confidence: 0.70

Reasoning: "Both teams have strong attacking records..."
```

**Result:** ✅ Comprehensive expert prediction with all markets covered

---

### Scenario 2: Match Outcome Only
**Use Case:** You only want to predict the match result

```
Match ID: 1416498
Home Win: 0.50, Draw: 0.30, Away Win: 0.20
Confidence: 0.80

BTTS: (skip)
Total Goals: (skip)

Reasoning: "Home team advantage, strong recent form"
```

**Result:** ✅ Valid prediction focusing only on match outcome

---

### Scenario 3: Match Outcome + BTTS
**Use Case:** You have insights on match result and goal-scoring

```
Match ID: 1416498
Home Win: 0.40, Draw: 0.35, Away Win: 0.25
Confidence: 0.75

BTTS Yes: 0.60, BTTS No: 0.40
BTTS Confidence: 0.80

Total Goals: (skip)

Reasoning: "Evenly matched teams, both likely to score"
```

**Result:** ✅ Valid prediction with match outcome and BTTS

---

### Scenario 4: Match Outcome + Total Goals
**Use Case:** You have insights on match result and total goals

```
Match ID: 1416498
Home Win: 0.55, Draw: 0.25, Away Win: 0.20
Confidence: 0.85

BTTS: (skip)

Over 2.5: 0.70, Under 2.5: 0.30
Over 3.5: 0.45, Under 3.5: 0.55
Total Goals Confidence: 0.75

Reasoning: "Attacking teams, expect high-scoring match"
```

**Result:** ✅ Valid prediction with match outcome and total goals

---

## Validation Rules

### Required Fields:
✅ Match ID  
✅ Home Win Probability  
✅ Draw Probability  
✅ Away Win Probability  

### Optional Fields:
⭕ Match Outcome Confidence  
⭕ BTTS Yes Probability  
⭕ BTTS No Probability  
⭕ BTTS Confidence  
⭕ Total Goals Over 2.5 Probability  
⭕ Total Goals Under 2.5 Probability  
⭕ Total Goals Over 3.5 Probability  
⭕ Total Goals Under 3.5 Probability  
⭕ Total Goals Confidence  
⭕ Reasoning  

### Validation Checks:
1. **Match Outcome:** Home + Draw + Away must sum to 1.0 (±0.01 tolerance)
2. **BTTS:** If both Yes and No are provided, they must sum to 1.0 (±0.01 tolerance)
3. **Probabilities:** All probability values must be between 0 and 1
4. **Reasoning:** Maximum 2000 characters

---

## Tips for Experts

### 1. Start Simple
- Begin with just match outcome predictions
- Add BTTS and Total Goals as you gain confidence
- You don't need to fill all fields for every match

### 2. Use Confidence Scores Wisely
- High confidence (0.8-1.0): Strong conviction based on solid analysis
- Medium confidence (0.6-0.8): Reasonable prediction with some uncertainty
- Low confidence (0.4-0.6): Uncertain prediction, use sparingly

### 3. BTTS Predictions
- Consider team attacking/defensive records
- Check head-to-head history
- Factor in missing key players (strikers/defenders)

### 4. Total Goals Predictions
- Analyze team scoring averages
- Consider match importance (defensive vs attacking approach)
- Weather conditions can affect goal totals

### 5. Reasoning Field
- Explain your key factors
- Mention team news, form, tactics
- Helps build trust with users

---

## Common Mistakes to Avoid

❌ **Mistake 1:** Probabilities don't sum to 1.0
```
Home: 0.50, Draw: 0.30, Away: 0.30 = 1.10 ❌
```
✅ **Correct:**
```
Home: 0.45, Draw: 0.30, Away: 0.25 = 1.00 ✅
```

❌ **Mistake 2:** BTTS probabilities don't sum to 1.0
```
BTTS Yes: 0.70, BTTS No: 0.40 = 1.10 ❌
```
✅ **Correct:**
```
BTTS Yes: 0.70, BTTS No: 0.30 = 1.00 ✅
```

❌ **Mistake 3:** Probability values outside 0-1 range
```
Home: 1.5 ❌ (must be ≤ 1.0)
```
✅ **Correct:**
```
Home: 0.50 ✅
```

❌ **Mistake 4:** Providing only one BTTS probability
```
BTTS Yes: 0.60, BTTS No: (empty) ❌
```
✅ **Correct Option 1:** Provide both
```
BTTS Yes: 0.60, BTTS No: 0.40 ✅
```
✅ **Correct Option 2:** Skip both
```
BTTS Yes: (empty), BTTS No: (empty) ✅
```

---

## Form Behavior

### Real-Time Feedback:
- ✅ Percentage calculations update as you type
- ✅ Validation warnings appear immediately
- ✅ Total sum displayed for match outcome and BTTS

### Form Submission:
1. Click "Create Prediction" button
2. Form validates all fields
3. If valid: Prediction created with PENDING status
4. Success message appears
5. Automatic redirect to Expert Dashboard after 1.5 seconds

### After Submission:
- Prediction appears in Expert Dashboard with PENDING status
- Admin must approve before it becomes PUBLISHED
- You can view/edit PENDING predictions
- Cannot edit APPROVED or PUBLISHED predictions

---

## Keyboard Shortcuts

- **Tab:** Move to next field
- **Shift + Tab:** Move to previous field
- **Enter:** Submit form (when focused on submit button)
- **Esc:** Cancel (returns to Expert Dashboard)

---

## Mobile Responsiveness

The form is fully responsive and works on:
- ✅ Desktop (1920x1080+)
- ✅ Laptop (1366x768+)
- ✅ Tablet (768x1024+)
- ✅ Mobile (375x667+)

---

## Accessibility

- ✅ All form fields have proper labels
- ✅ Keyboard navigation supported
- ✅ Screen reader compatible
- ✅ High contrast mode supported
- ✅ Dark mode supported

---

## Support

If you encounter any issues:
1. Check validation messages
2. Ensure probabilities sum correctly
3. Verify all required fields are filled
4. Contact admin if problems persist

---

**Happy Predicting! ⚽🎯**

