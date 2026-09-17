# User Roles and Permissions Matrix
## Soccer Predictions Platform

**Version**: 1.0  
**Last Updated**: 2025-10-09  
**Related**: COMPREHENSIVE_REQUIREMENTS_DOCUMENT.md

---

## Permission Categories

This document provides a comprehensive matrix of permissions for each user role in the Soccer Predictions Platform.

---

## 1. Regular User Permissions

### 1.1 Subscription Tier Access Matrix

| Feature | Free | Basic | Premium | Pro |
|---------|:----:|:-----:|:-------:|:---:|
| **Predictions** |
| Daily prediction limit | 3 | 10 | Unlimited | Unlimited |
| View confidence levels | ❌ | ✅ | ✅ | ✅ |
| View prediction analysis | ❌ | ✅ | ✅ | ✅ |
| View key factors | ❌ | ✅ | ✅ | ✅ |
| **Markets** |
| 1X2 (Home/Draw/Away) | ✅ | ✅ | ✅ | ✅ |
| Both Teams to Score (BTTS) | ❌ | ✅ | ✅ | ✅ |
| Over/Under Goals | ❌ | ✅ | ✅ | ✅ |
| Correct Score | ❌ | ❌ | ✅ | ✅ |
| Double Chance | ❌ | ❌ | ✅ | ✅ |
| Handicap | ❌ | ❌ | ✅ | ✅ |
| **Prediction Sources** |
| ML predictions | ✅ | ✅ | ✅ | ✅ |
| Expert predictions | ❌ | ❌ | ✅ | ✅ |
| Admin predictions | ❌ | ❌ | ✅ | ✅ |
| **Historical Data** |
| Accuracy history | 7 days | 30 days | 90 days | Unlimited |
| Personal prediction history | 7 days | 30 days | 90 days | Unlimited |
| Expert performance history | ❌ | ❌ | 30 days | Unlimited |
| **Analytics** |
| Basic statistics | ✅ | ✅ | ✅ | ✅ |
| Advanced analytics | ❌ | ❌ | ❌ | ✅ |
| Performance trends | ❌ | ❌ | ✅ | ✅ |
| Custom reports | ❌ | ❌ | ❌ | ✅ |
| **Features** |
| Favorite teams/leagues | ✅ | ✅ | ✅ | ✅ |
| Email notifications | ✅ | ✅ | ✅ | ✅ |
| In-app notifications | ✅ | ✅ | ✅ | ✅ |
| Priority support | ❌ | ❌ | ✅ | ✅ |
| API access | ❌ | ❌ | ❌ | ✅ |
| Export data | ❌ | ❌ | ✅ | ✅ |

### 1.2 Regular User Permissions (All Tiers)

| Permission | Description | Access |
|------------|-------------|:------:|
| **Account Management** |
| Create account | Register with email/password | ✅ |
| Login/Logout | Authenticate with credentials | ✅ |
| Update profile | Edit name, username, avatar | ✅ |
| Change password | Update password with verification | ✅ |
| Delete account | Request account deletion (GDPR) | ✅ |
| **Predictions** |
| View predictions | Access predictions based on tier | ✅ |
| View match details | See match information and stats | ✅ |
| View historical predictions | Access past predictions (tier-limited) | ✅ |
| Provide feedback | Rate and comment on predictions | ✅ |
| **Preferences** |
| Set favorite teams | Select favorite teams | ✅ |
| Set favorite leagues | Select favorite leagues | ✅ |
| Configure notifications | Email and in-app settings | ✅ |
| Set theme | Light/dark/auto mode | ✅ |
| **Subscription** |
| View subscription | See current tier and features | ✅ |
| Upgrade subscription | Move to higher tier | ✅ |
| Downgrade subscription | Move to lower tier | ✅ |
| Cancel subscription | End paid subscription | ✅ |
| View billing history | See payment history | ✅ |
| **Prohibited Actions** |
| Create predictions | Only experts can create | ❌ |
| Override predictions | Only experts can override | ❌ |
| Approve predictions | Only admins can approve | ❌ |
| Manage users | Only admins can manage | ❌ |
| Access admin tools | Only admins have access | ❌ |

---

## 2. Expert User Permissions

### 2.1 Expert Verification Levels

| Level | Predictions | Accuracy | Status | Capabilities |
|-------|-------------|----------|--------|--------------|
| **Pending** | 0 | N/A | Awaiting approval | None |
| **Level 1-3** | 0-100 | 60-65% | Novice Expert | Basic override |
| **Level 4-6** | 100-500 | 65-70% | Intermediate Expert | Full override + templates |
| **Level 7-9** | 500-2000 | 70-75% | Advanced Expert | All features + mentoring |
| **Level 10** | 2000+ | 75%+ | Master Expert | All features + featured status |

### 2.2 Expert User Permissions

| Permission | Description | Access |
|------------|-------------|:------:|
| **All Regular User Permissions** | Inherits all regular user capabilities | ✅ |
| **Prediction Creation** |
| View ML baseline | See ML predictions with confidence | ✅ |
| Create manual prediction | Create prediction from scratch | ✅ |
| Override ML prediction | Modify ML prediction | ✅ |
| Adjust confidence | Change confidence level (±30%) | ✅ |
| Set prediction markets | Define multiple betting markets | ✅ |
| Add analysis | Provide detailed analysis (min 100 chars) | ✅ |
| Specify key factors | List influencing factors (min 3) | ✅ |
| **Expert Tools** |
| Access expert dashboard | View personal performance metrics | ✅ |
| View ML comparison | Compare performance vs ML baseline | ✅ |
| Access analytics tools | Advanced match analysis tools | ✅ |
| Use backtesting | Test strategies on historical data | ✅ |
| Create templates | Save reusable prediction templates | ✅ |
| View expert rankings | See leaderboard and rankings | ✅ |
| **Collaboration** |
| Comment on predictions | Discuss with other experts | ✅ |
| View expert discussions | Access expert forums | ✅ |
| Mentor novice experts | Guide new experts (Level 7+) | ✅ (Level 7+) |
| **Performance Tracking** |
| View accuracy metrics | Overall and by specialization | ✅ |
| View override performance | Track override vs ML accuracy | ✅ |
| View engagement metrics | Followers, views, ratings | ✅ |
| View reputation score | Expert reputation and level | ✅ |
| Export performance data | Download personal analytics | ✅ |
| **Specialization** |
| Set league specialties | Define expert leagues | ✅ |
| Set team specialties | Define expert teams | ✅ |
| Set market specialties | Define expert markets | ✅ |
| Update specialties | Modify specialization areas | ✅ |
| **Prohibited Actions** |
| Approve other experts | Only admins can approve | ❌ |
| Approve predictions | Only admins can approve high-stakes | ❌ |
| Manage users | Only admins can manage | ❌ |
| Access audit logs | Only admins have full access | ❌ |
| Configure system | Only admins can configure | ❌ |

### 2.3 Expert Specialization Matrix

| Specialization Type | Examples | Max Selections |
|---------------------|----------|----------------|
| **League** | Premier League, La Liga, Serie A, Bundesliga | 5 |
| **Team** | Manchester United, Real Madrid, Bayern Munich | 10 |
| **Market** | 1X2, BTTS, Over/Under, Correct Score | 3 |
| **Geographic** | England, Spain, Italy, Germany | 3 |
| **Competition Type** | Domestic League, Cup, International | 2 |

---

## 3. Admin User Permissions

### 3.1 Admin Hierarchy

| Level | Role | Description | Permissions |
|-------|------|-------------|-------------|
| **3** | Super Admin | Full unrestricted access | All permissions |
| **2** | Admin | Standard administrative access | Most permissions |
| **1** | Moderator | Limited admin access | Content moderation only |

### 3.2 Admin User Permissions

| Permission | Super Admin | Admin | Moderator |
|------------|:-----------:|:-----:|:---------:|
| **All Expert User Permissions** | ✅ | ✅ | ✅ |
| **User Management** |
| View all users | ✅ | ✅ | ✅ |
| Create user accounts | ✅ | ✅ | ❌ |
| Update user profiles | ✅ | ✅ | ❌ |
| Suspend user accounts | ✅ | ✅ | ✅ |
| Delete user accounts | ✅ | ❌ | ❌ |
| Reset user passwords | ✅ | ✅ | ❌ |
| Manage user roles | ✅ | ✅ | ❌ |
| View user activity logs | ✅ | ✅ | ✅ |
| **Expert Management** |
| Review expert applications | ✅ | ✅ | ❌ |
| Approve expert applications | ✅ | ✅ | ❌ |
| Reject expert applications | ✅ | ✅ | ❌ |
| Verify expert credentials | ✅ | ✅ | ❌ |
| Monitor expert performance | ✅ | ✅ | ✅ |
| Suspend expert status | ✅ | ✅ | ❌ |
| Revoke expert status | ✅ | ❌ | ❌ |
| Set expert levels | ✅ | ✅ | ❌ |
| Feature top experts | ✅ | ✅ | ❌ |
| **Prediction Management** |
| View all predictions | ✅ | ✅ | ✅ |
| Create admin predictions | ✅ | ✅ | ❌ |
| Override any prediction | ✅ | ✅ | ❌ |
| Approve high-stakes predictions | ✅ | ✅ | ❌ |
| Void predictions | ✅ | ✅ | ❌ |
| Settle predictions | ✅ | ✅ | ❌ |
| Moderate prediction comments | ✅ | ✅ | ✅ |
| Delete inappropriate content | ✅ | ✅ | ✅ |
| **System Configuration** |
| Configure ML parameters | ✅ | ❌ | ❌ |
| Set confidence thresholds | ✅ | ✅ | ❌ |
| Configure approval requirements | ✅ | ✅ | ❌ |
| Manage subscription tiers | ✅ | ❌ | ❌ |
| Configure API integrations | ✅ | ❌ | ❌ |
| Manage notification settings | ✅ | ✅ | ❌ |
| Configure system settings | ✅ | ❌ | ❌ |
| **Analytics & Reporting** |
| Access system analytics | ✅ | ✅ | ✅ |
| View prediction performance | ✅ | ✅ | ✅ |
| View user engagement metrics | ✅ | ✅ | ✅ |
| View revenue metrics | ✅ | ✅ | ❌ |
| Generate compliance reports | ✅ | ✅ | ❌ |
| Export analytics data | ✅ | ✅ | ❌ |
| **Audit & Compliance** |
| Access full audit trail | ✅ | ✅ | ❌ |
| View data access logs | ✅ | ✅ | ❌ |
| Monitor permission changes | ✅ | ✅ | ❌ |
| Track security incidents | ✅ | ✅ | ❌ |
| Generate GDPR reports | ✅ | ✅ | ❌ |
| Manage data retention | ✅ | ❌ | ❌ |
| Handle deletion requests | ✅ | ✅ | ❌ |
| **Admin Management** |
| Create admin accounts | ✅ | ❌ | ❌ |
| Manage admin permissions | ✅ | ❌ | ❌ |
| View admin activity logs | ✅ | ✅ | ❌ |
| Revoke admin access | ✅ | ❌ | ❌ |

---

## 4. Permission Inheritance Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  Permission Inheritance                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Super Admin (Level 3)                   │   │
│  │  • All Admin permissions                             │   │
│  │  • System configuration                              │   │
│  │  • User deletion                                     │   │
│  │  • Admin management                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          │ Inherits                         │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Admin (Level 2)                         │   │
│  │  • All Moderator permissions                         │   │
│  │  • User management                                   │   │
│  │  • Expert approval                                   │   │
│  │  • Prediction approval                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          │ Inherits                         │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Moderator (Level 1)                     │   │
│  │  • All Expert permissions                            │   │
│  │  • Content moderation                                │   │
│  │  • User suspension                                   │   │
│  │  • View analytics                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          │ Inherits                         │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Expert User                             │   │
│  │  • All Regular User permissions                      │   │
│  │  • Create predictions                                │   │
│  │  • Override ML predictions                           │   │
│  │  • Access expert tools                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          │ Inherits                         │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Regular User                            │   │
│  │  • View predictions (tier-based)                     │   │
│  │  • Manage profile                                    │   │
│  │  • Provide feedback                                  │   │
│  │  • Manage subscription                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. API Endpoint Permissions

| Endpoint | Regular | Expert | Moderator | Admin | Super Admin |
|----------|:-------:|:------:|:---------:|:-----:|:-----------:|
| **Authentication** |
| POST /auth/register | ✅ | ✅ | ✅ | ✅ | ✅ |
| POST /auth/login | ✅ | ✅ | ✅ | ✅ | ✅ |
| POST /auth/logout | ✅ | ✅ | ✅ | ✅ | ✅ |
| POST /auth/refresh | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Users** |
| GET /users/me | ✅ | ✅ | ✅ | ✅ | ✅ |
| PUT /users/me | ✅ | ✅ | ✅ | ✅ | ✅ |
| GET /users | ❌ | ❌ | ✅ | ✅ | ✅ |
| GET /users/{id} | ❌ | ❌ | ✅ | ✅ | ✅ |
| PUT /users/{id} | ❌ | ❌ | ❌ | ✅ | ✅ |
| DELETE /users/{id} | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Predictions** |
| GET /predictions | ✅ | ✅ | ✅ | ✅ | ✅ |
| GET /predictions/{id} | ✅ | ✅ | ✅ | ✅ | ✅ |
| POST /predictions | ❌ | ✅ | ✅ | ✅ | ✅ |
| PUT /predictions/{id} | ❌ | ✅ | ✅ | ✅ | ✅ |
| DELETE /predictions/{id} | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Expert** |
| POST /expert/apply | ✅ | ❌ | ❌ | ❌ | ❌ |
| POST /expert/override | ❌ | ✅ | ✅ | ✅ | ✅ |
| GET /expert/analytics | ❌ | ✅ | ✅ | ✅ | ✅ |
| GET /expert/dashboard | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Admin** |
| GET /admin/users | ❌ | ❌ | ✅ | ✅ | ✅ |
| POST /admin/approve-expert | ❌ | ❌ | ❌ | ✅ | ✅ |
| POST /admin/approve-prediction | ❌ | ❌ | ❌ | ✅ | ✅ |
| GET /admin/audit | ❌ | ❌ | ❌ | ✅ | ✅ |
| GET /admin/stats | ❌ | ❌ | ✅ | ✅ | ✅ |
| PUT /admin/config | ❌ | ❌ | ❌ | ❌ | ✅ |

---

**For detailed requirements, refer to**: `COMPREHENSIVE_REQUIREMENTS_DOCUMENT.md`

