# KAN-26: Multi-Source Prediction Priority System - Comprehensive Analysis

**Project**: Soccer Predictions Platform  
**Jira Task**: KAN-26 - Implement Expert API endpoints for prediction management  
**Document Type**: Technical Analysis & Implementation Planning  
**Status**: Analysis Complete - Ready for Implementation  
**Date**: 2025-10-12  
**Author**: Augment Code (Co-authored by Steph)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Multi-Source Prediction Priority System](#multi-source-prediction-priority-system)
4. [Data Model & Storage Strategy](#data-model--storage-strategy)
5. [Service Layer Architecture](#service-layer-architecture)
6. [Frontend Display Strategy](#frontend-display-strategy)
7. [User Role Integration](#user-role-integration)
8. [API Integration Points](#api-integration-points)
9. [Audit Trail & Logging](#audit-trail--logging)
10. [Caching Strategy](#caching-strategy)
11. [Recommendations & Implementation Approach](#recommendations--implementation-approach)
12. [Risks & Mitigation](#risks--mitigation)
13. [Implementation Roadmap](#implementation-roadmap)
14. [Success Metrics](#success-metrics)
15. [Appendices](#appendices)

---

## Executive Summary

### Overview

The Soccer Predictions Platform is implementing a **hybrid prediction system** that combines predictions from multiple sources with different priority levels. This document provides a comprehensive analysis for implementing KAN-26 (Expert API endpoints) and the broader multi-source prediction priority system.

### Current State

- ✅ **Frontend**: Live with API-Football V3 Pro integration
- ✅ **Backend**: Database models, authentication, basic API structure complete
- ✅ **Authentication**: JWT-based auth with role-based access control (in progress)
- 🔄 **Expert API**: Placeholder endpoints exist but lack business logic

### Three Prediction Sources (Priority Order)

1. **Expert User Predictions** (HIGHEST PRIORITY - Level 100)
   - Source: Manual predictions created by Expert Users
   - Characteristics: Human expertise, manual analysis
   - Visibility: Premium/Pro tiers only

2. **LLM-Generated Predictions** (MEDIUM PRIORITY - Level 50)
   - Source: Large Language Model predictions (future ML/AI integration)
   - Characteristics: AI-generated, automated
   - Visibility: Basic/Premium/Pro tiers

3. **API-Football Predictions** (LOWER PRIORITY - Level 25)
   - Source: API-Football V3 Pro `/predictions` endpoint
   - Characteristics: Third-party API, currently implemented
   - Visibility: All tiers (Free+)

### Critical Challenge

Design a multi-source prediction priority system that:
- Handles predictions from multiple sources with different priority levels
- Maintains data integrity and audit trails
- Provides tier-based access control
- Delivers optimal user experience
- Supports future prediction sources

### Key Recommendations

1. **Priority Logic**: Waterfall/cascade approach with tier-based filtering
2. **Data Model**: Add `priority_level` field, store ALL predictions
3. **Service Architecture**: Create `PredictionAggregatorService` as central orchestrator
4. **Frontend Display**: Tiered visibility with clear visual indicators
5. **Audit Trail**: Comprehensive logging of all prediction lifecycle events

---

## Current State Analysis

### 1.1 Jira Project Status

#### Completed Tasks (DONE Status)

| Task | Summary | Relevance to KAN-26 |
|------|---------|---------------------|
| KAN-122 | POST /auth/register | ✅ User creation for experts |
| KAN-123 | POST /auth/login | ✅ Expert authentication |
| KAN-124 | POST /auth/logout | ✅ Session management |
| KAN-125 | POST /auth/refresh | ✅ Token refresh |
| KAN-126 | GET /users/me | ✅ Expert profile retrieval |
| KAN-128 | PUT /users/me/password | ✅ Security |
| KAN-138 | Pydantic schemas | ✅ Request/response models |

#### In Progress Tasks

| Task | Summary | Blocking KAN-26? |
|------|---------|------------------|
| KAN-25 | Public API endpoints | ⚠️ Partial - provides foundation |
| KAN-24 | Role-based permissions | ⚠️ **CRITICAL** - Required for expert permissions |
| KAN-127 | PUT /users/me | ⚠️ Partial - expert profile updates |
| KAN-139 | Subscription tier middleware | ⚠️ Partial - tier-based access |
| KAN-140 | Error handling | ⚠️ Partial - validation logic |
| KAN-141 | Unit tests | ⚠️ Partial - testing framework |
| KAN-142 | API documentation | ⚠️ Partial - OpenAPI docs |

#### Dependencies for KAN-26

**Hard Dependencies** (Must be complete):
1. ✅ **KAN-17**: User models (DONE)
2. ✅ **KAN-23**: JWT authentication (DONE)
3. ⚠️ **KAN-24**: RBAC system (IN PROGRESS) - **BLOCKER**
4. ⚠️ **KAN-18**: Prediction models (Assumed complete based on codebase)
5. ❌ **KAN-33**: ML models (NOT STARTED) - **BLOCKER**

**Soft Dependencies** (Nice to have):
- KAN-28: Redis caching (✅ DONE)
- KAN-138: Pydantic schemas (✅ DONE)
- KAN-139: Subscription tier middleware (🔄 IN PROGRESS)

### 1.2 Database Schema Analysis

#### Predictions Schema (16 tables)

The predictions schema contains 16 tables organized into 4 functional groups:

| Group | Tables | Purpose |
|-------|--------|---------|
| **Core Predictions** | 5 tables | Predictions, overrides, audit, results, markets |
| **Match Data** | 3 tables | Matches, results, statistics |
| **Analytics & Engagement** | 3 tables | Analytics, views, feedback |
| **Reference Data** | 3 tables | Leagues, teams, templates |

#### Core Prediction Model

```python
class Prediction(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Core predictions table
    Supports hybrid ML + Expert prediction system
    """
    __tablename__ = "predictions"
    
    # Match Reference
    match_id = uuid_fk('predictions.matches.id', nullable=False)
    
    # Source Attribution
    source = Column(Enum(PredictionSource), nullable=False)
    created_by = uuid_fk('users.users.id', nullable=False)
    ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True)
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=True)
    
    # Probabilities (must sum to 1.0)
    home_win_prob = Column(DECIMAL(5, 4), nullable=False)
    draw_prob = Column(DECIMAL(5, 4), nullable=False)
    away_win_prob = Column(DECIMAL(5, 4), nullable=False)
    
    # Confidence & Reasoning
    confidence_score = Column(DECIMAL(5, 4), nullable=False)
    reasoning = Column(Text)
    key_factors = Column(JSONB)
    
    # Status & Approval
    status = Column(Enum(PredictionStatus), nullable=False, default=PredictionStatus.PENDING)
    approved_by = uuid_fk('users.users.id', nullable=True)
    approved_at = Column(DateTime)
    published_at = Column(DateTime)
```

#### Current PredictionSource Enum

```python
class PredictionSource(str, enum.Enum):
    """Prediction source enumeration"""
    ML_BASELINE = "ml_baseline"
    EXPERT_OVERRIDE = "expert_override"
    EXPERT_MANUAL = "expert_manual"
    ADMIN_MANUAL = "admin_manual"
```

#### Prediction Override Model

```python
class PredictionOverride(Base, UUIDMixin, TimestampMixin):
    """Expert overrides of ML predictions"""
    __tablename__ = "prediction_overrides"
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    expert_user_id = uuid_fk('users.users.id', nullable=False)
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)
    
    # Original ML Prediction
    original_ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True)
    original_probabilities = Column(JSONB, nullable=False)
    original_confidence = Column(DECIMAL(5, 4))
    
    # New Expert Prediction
    new_probabilities = Column(JSONB, nullable=False)
    new_confidence = Column(DECIMAL(5, 4), nullable=False)
    
    # Override Details
    override_reason = Column(Text, nullable=False)
    changes_made = Column(JSONB)
```

#### Key Observations

1. ✅ **Source tracking exists**: `source` field with enum values
2. ✅ **Override mechanism exists**: Separate `prediction_overrides` table
3. ✅ **Audit trail exists**: `prediction_audit` table for lifecycle tracking
4. ⚠️ **No priority field**: Current schema doesn't have explicit priority levels
5. ⚠️ **No LLM source**: Current enum doesn't include LLM-generated predictions
6. ⚠️ **No API-Football source**: Current enum doesn't include API-Football predictions

### 1.3 Backend Implementation Status

#### Existing Expert API Endpoints (Placeholder)

```python
# backend/app/api/v1/endpoints/expert.py

@router.get("/dashboard")
async def get_expert_dashboard(
    current_user: User = Depends(get_current_expert_user)
):
    """Get expert dashboard data"""
    # Placeholder implementation
    pass

@router.get("/ml-baseline")
async def get_ml_baseline_predictions(
    match_id: str,
    current_user: User = Depends(get_current_expert_user)
):
    """Get ML baseline predictions for a match"""
    # Placeholder implementation
    pass

@router.post("/predictions/manual")
async def create_manual_prediction(
    match_id: str,
    prediction_data: Dict[str, Any],
    current_user: User = Depends(get_current_verified_expert_user)
):
    """Create manual prediction"""
    # Placeholder implementation
    pass

@router.post("/predictions/override")
async def override_ml_prediction(
    match_id: str,
    override_data: Dict[str, Any],
    current_user: User = Depends(get_current_verified_expert_user)
):
    """Override ML prediction"""
    # Placeholder implementation
    pass
```

**Status**: Placeholder implementations exist but lack business logic.

#### Existing Services

1. **PredictionCacheService** (✅ Complete)
   - Caches predictions in Redis
   - Supports ML predictions, match predictions
   - TTL-based expiration

2. **Authentication Services** (✅ Complete)
   - JWT token generation/validation
   - User authentication
   - Role-based access control (in progress)

3. **Prediction Services** (❌ Not Started)
   - Expert prediction creation
   - Prediction override logic
   - Priority resolution
   - Prediction aggregation

### 1.4 Frontend Implementation Status

#### Current API-Football Integration

The frontend currently uses API-Football V3 Pro integration:

```typescript
// frontend/src/services/prediction.service.ts

export interface PredictionListItem {
  id: string;
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  match_date: string;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  confidence_level: number | null;
  source: string;
  status: string;
  created_at: string;
}
```

#### Visual Indicators

- ⭐ Star icon for real API predictions (first 5 matches per page)
- No icon for randomized default predictions

#### Three-Tier Service Architecture

1. **API Client**: HTTP requests to backend
2. **Mapper**: Transform API responses to frontend models
3. **High-level Service**: Business logic, caching

---

## Multi-Source Prediction Priority System

### 3.1 Prediction Priority Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│              PREDICTION PRIORITY WATERFALL                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ EXPERT USER PREDICTIONS (HIGHEST PRIORITY)             │
│     ├── Source: expert_manual or expert_override            │
│     ├── Priority Level: 100                                 │
│     ├── Characteristics: Human expertise, manual analysis   │
│     ├── Visibility: Premium/Pro tiers only                  │
│     └── Fallback: If no expert prediction exists → Next     │
│                                                             │
│  2️⃣ LLM-GENERATED PREDICTIONS (MEDIUM PRIORITY)            │
│     ├── Source: llm_generated (NEW)                         │
│     ├── Priority Level: 50                                  │
│     ├── Characteristics: AI-generated, automated            │
│     ├── Visibility: Basic/Premium/Pro tiers                 │
│     └── Fallback: If no LLM prediction exists → Next        │
│                                                             │
│  3️⃣ API-FOOTBALL PREDICTIONS (LOWER PRIORITY / DEFAULT)    │
│     ├── Source: api_football_baseline (NEW)                 │
│     ├── Priority Level: 25                                  │
│     ├── Characteristics: Third-party API, external          │
│     ├── Visibility: All tiers (Free+)                       │
│     └── Fallback: If no API prediction exists → Randomized  │
│                                                             │
│  4️⃣ RANDOMIZED DEFAULT (FALLBACK)                          │
│     ├── Source: default_randomized                          │
│     ├── Priority Level: 0                                   │
│     ├── Characteristics: Placeholder, no real data          │
│     ├── Visibility: All tiers                               │
│     └── Purpose: Ensure UI always has data to display       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Priority Resolution Algorithm

```python
def get_prediction_for_match(match_id: str, user_tier: str) -> Prediction:
    """
    Waterfall logic to retrieve highest priority prediction

    Args:
        match_id: Match identifier
        user_tier: User's subscription tier (free, basic, premium, pro)

    Returns:
        Highest priority prediction available to user's tier
    """
    # 1. Check for Expert prediction (if user has access)
    if user_tier in ['premium', 'pro']:
        expert_pred = get_expert_prediction(match_id)
        if expert_pred and expert_pred.status == 'published':
            return expert_pred

    # 2. Check for LLM prediction (if user has access)
    if user_tier in ['basic', 'premium', 'pro']:
        llm_pred = get_llm_prediction(match_id)
        if llm_pred and llm_pred.status == 'published':
            return llm_pred

    # 3. Check for API-Football prediction (all tiers)
    api_pred = get_api_football_prediction(match_id)
    if api_pred:
        return api_pred

    # 4. Fallback to randomized default
    return generate_randomized_prediction(match_id)
```

### 3.3 Conflict Resolution Strategy

**Scenario**: Multiple predictions exist for the same match.

**Resolution Rules**:
1. **Priority-based selection**: Always select highest priority source
2. **Status filtering**: Only consider `published` predictions
3. **Timestamp consideration**: If multiple predictions at same priority level, use most recent
4. **Audit trail**: Log which prediction was selected and why

**Example**:
```
Match ID: abc-123
- Expert prediction (priority 100, published, created_at: 2025-10-12 10:00)
- LLM prediction (priority 50, published, created_at: 2025-10-12 09:00)
- API-Football prediction (priority 25, published, created_at: 2025-10-12 08:00)

Result: Expert prediction selected (highest priority)
Audit log: "Selected expert_manual prediction (priority 100) over llm_generated (50) and api_football_baseline (25)"
```

### 3.4 Tier-Based Access Control

| User Tier | Expert Predictions | LLM Predictions | API-Football | Source Details |
|-----------|-------------------|-----------------|--------------|----------------|
| **Free** | ❌ Hidden | ❌ Hidden | ✅ Visible | ❌ No source info |
| **Basic** | ❌ Hidden | ✅ Visible | ✅ Visible | ⚠️ Basic source info |
| **Premium** | ✅ Visible | ✅ Visible | ✅ Visible | ✅ Full source info |
| **Pro** | ✅ Visible | ✅ Visible | ✅ Visible | ✅ All sources + comparison |

---

## Data Model & Storage Strategy

### 4.1 Proposed Schema Changes

#### Option A: Add Priority Field to Existing Table (RECOMMENDED)

```sql
-- Add priority_level field
ALTER TABLE predictions.predictions
ADD COLUMN priority_level INTEGER DEFAULT 0
CHECK (priority_level >= 0 AND priority_level <= 100);

-- Add superseded_by field for tracking prediction supersession
ALTER TABLE predictions.predictions
ADD COLUMN superseded_by UUID REFERENCES predictions.predictions(id);

-- Create composite index for priority queries
CREATE INDEX idx_predictions_priority
ON predictions.predictions(match_id, priority_level DESC, published_at DESC)
WHERE status = 'published' AND deleted_at IS NULL;
```

**Rationale**:
- ✅ Simple implementation
- ✅ Maintains existing relationships
- ✅ Easy to query: `ORDER BY priority_level DESC, published_at DESC`
- ✅ Supports future priority levels
- ✅ No additional JOINs required

#### Option B: Create Separate Priority Table (Alternative)

```sql
CREATE TABLE predictions.prediction_priorities (
    id UUID PRIMARY KEY,
    match_id UUID NOT NULL REFERENCES predictions.matches(id),
    active_prediction_id UUID NOT NULL REFERENCES predictions.predictions(id),
    priority_level INTEGER NOT NULL,
    superseded_predictions JSONB,  -- Array of superseded prediction IDs
    selection_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Rationale**:
- ✅ Explicit priority tracking
- ✅ Historical record of priority changes
- ❌ More complex queries (requires JOIN)
- ❌ Additional table to maintain

**Recommendation**: **Option A** - Add `priority_level` field to existing table.

### 4.2 Updated PredictionSource Enum

```python
class PredictionSource(str, enum.Enum):
    """Prediction source enumeration"""
    # Existing
    ML_BASELINE = "ml_baseline"  # Legacy ML predictions
    EXPERT_OVERRIDE = "expert_override"
    EXPERT_MANUAL = "expert_manual"
    ADMIN_MANUAL = "admin_manual"

    # NEW - Multi-source support
    LLM_GENERATED = "llm_generated"  # LLM predictions (priority 50)
    API_FOOTBALL_BASELINE = "api_football_baseline"  # API-Football (priority 25)
    DEFAULT_RANDOMIZED = "default_randomized"  # Fallback (priority 0)
```

### 4.3 Priority Level Mapping

```python
PREDICTION_PRIORITY_MAP = {
    PredictionSource.EXPERT_MANUAL: 100,
    PredictionSource.EXPERT_OVERRIDE: 100,
    PredictionSource.ADMIN_MANUAL: 100,
    PredictionSource.LLM_GENERATED: 50,
    PredictionSource.ML_BASELINE: 40,  # Legacy ML
    PredictionSource.API_FOOTBALL_BASELINE: 25,
    PredictionSource.DEFAULT_RANDOMIZED: 0,
}
```

### 4.4 Storage Strategy: Store ALL Predictions

**Question**: Should we store all predictions or only the highest priority one?

**Recommendation**: **Store ALL predictions** with status tracking.

**Rationale**:
1. ✅ **Audit trail**: Complete history of all prediction sources
2. ✅ **A/B testing**: Compare accuracy across sources
3. ✅ **Fallback**: If expert prediction is voided, can fall back to LLM
4. ✅ **Analytics**: Track which sources perform best
5. ✅ **Transparency**: Users can see all available predictions (Pro tier)

**Implementation**:
```sql
-- Multiple predictions per match, different sources
INSERT INTO predictions.predictions (match_id, source, priority_level, status, ...)
VALUES
  ('match-123', 'expert_manual', 100, 'published', ...),
  ('match-123', 'llm_generated', 50, 'published', ...),
  ('match-123', 'api_football_baseline', 25, 'published', ...);

-- Query for highest priority published prediction
SELECT * FROM predictions.predictions
WHERE match_id = 'match-123'
  AND status = 'published'
  AND deleted_at IS NULL
ORDER BY priority_level DESC, published_at DESC
LIMIT 1;
```

### 4.5 Database Migration Script

```sql
-- Migration: Add multi-source prediction priority support
-- Version: 2025-10-12_add_prediction_priority

BEGIN;

-- 1. Add priority_level field
ALTER TABLE predictions.predictions
ADD COLUMN priority_level INTEGER DEFAULT 0
CHECK (priority_level >= 0 AND priority_level <= 100);

-- 2. Add superseded_by field
ALTER TABLE predictions.predictions
ADD COLUMN superseded_by UUID REFERENCES predictions.predictions(id);

-- 3. Create index for priority queries
CREATE INDEX idx_predictions_priority
ON predictions.predictions(match_id, priority_level DESC, published_at DESC)
WHERE status = 'published' AND deleted_at IS NULL;

-- 4. Update existing predictions with priority levels
UPDATE predictions.predictions
SET priority_level = CASE source
    WHEN 'expert_manual' THEN 100
    WHEN 'expert_override' THEN 100
    WHEN 'admin_manual' THEN 100
    WHEN 'ml_baseline' THEN 40
    ELSE 0
END;

-- 5. Add new enum values to PredictionSource
ALTER TYPE predictions.prediction_source
ADD VALUE IF NOT EXISTS 'llm_generated';

ALTER TYPE predictions.prediction_source
ADD VALUE IF NOT EXISTS 'api_football_baseline';

ALTER TYPE predictions.prediction_source
ADD VALUE IF NOT EXISTS 'default_randomized';

COMMIT;
```

---

## Service Layer Architecture

### 5.1 Proposed Service Structure

```
┌─────────────────────────────────────────────────────────────┐
│              PREDICTION SERVICE ARCHITECTURE                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Prediction Aggregator Service (NEW)          │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  get_prediction_for_match(match_id, user_tier) │  │   │
│  │  │  - Waterfall priority logic                     │  │   │
│  │  │  - Tier-based filtering                         │  │   │
│  │  │  - Caching layer                                │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Prediction Source Services                 │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │   │
│  │  │   Expert   │  │    LLM     │  │  API-Football  │  │   │
│  │  │  Service   │  │  Service   │  │    Service     │  │   │
│  │  └────────────┘  └────────────┘  └────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Data Access Layer                       │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  PostgreSQL (predictions schema)               │  │   │
│  │  │  Redis (caching layer)                         │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 PredictionAggregatorService (NEW)

```python
# backend/app/services/prediction_aggregator.py

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.predictions import Prediction, PredictionStatus
from app.services.prediction_cache import PredictionCacheService
from app.services.expert_prediction import ExpertPredictionService
from app.services.llm_prediction import LLMPredictionService
from app.services.api_football_prediction import APIFootballPredictionService
from app.services.prediction_audit import PredictionAuditService

class PredictionAggregatorService:
    """
    Aggregates predictions from multiple sources with priority logic
    Central orchestrator for multi-source prediction system
    """

    def __init__(self, db: Session, cache: PredictionCacheService):
        self.db = db
        self.cache = cache
        self.expert_service = ExpertPredictionService(db)
        self.llm_service = LLMPredictionService(db)
        self.api_football_service = APIFootballPredictionService(db)
        self.audit_service = PredictionAuditService(db)

    async def get_prediction_for_match(
        self,
        match_id: str,
        user_tier: str
    ) -> Prediction:
        """
        Get highest priority prediction for match based on user tier

        Waterfall logic:
        1. Expert prediction (Premium/Pro only)
        2. LLM prediction (Basic/Premium/Pro)
        3. API-Football prediction (All tiers)
        4. Randomized default (Fallback)

        Args:
            match_id: Match identifier
            user_tier: User's subscription tier (free, basic, premium, pro)

        Returns:
            Highest priority prediction available to user's tier
        """
        # Check cache first
        cache_key = f"prediction:{match_id}:{user_tier}"
        cached = await self.cache.get_cached_prediction(cache_key)
        if cached:
            return cached

        prediction = None
        alternatives = []

        # 1. Expert prediction (highest priority)
        if user_tier in ['premium', 'pro']:
            prediction = await self.expert_service.get_published_prediction(match_id)
            if prediction:
                await self.audit_service.log_prediction_selected(
                    prediction,
                    selection_reason="expert_priority",
                    alternatives=alternatives
                )
                await self.cache.cache_prediction(cache_key, prediction, ttl=300)
                return prediction

        # 2. LLM prediction (medium priority)
        if user_tier in ['basic', 'premium', 'pro']:
            prediction = await self.llm_service.get_published_prediction(match_id)
            if prediction:
                await self.audit_service.log_prediction_selected(
                    prediction,
                    selection_reason="llm_priority",
                    alternatives=alternatives
                )
                await self.cache.cache_prediction(cache_key, prediction, ttl=300)
                return prediction

        # 3. API-Football prediction (lower priority)
        prediction = await self.api_football_service.get_published_prediction(match_id)
        if prediction:
            await self.audit_service.log_prediction_selected(
                prediction,
                selection_reason="api_football_priority",
                alternatives=alternatives
            )
            await self.cache.cache_prediction(cache_key, prediction, ttl=300)
            return prediction

        # 4. Fallback to randomized default
        prediction = await self._generate_randomized_prediction(match_id)
        await self.audit_service.log_prediction_selected(
            prediction,
            selection_reason="randomized_fallback",
            alternatives=alternatives
        )
        return prediction

    async def get_all_predictions_for_match(
        self,
        match_id: str
    ) -> List[Prediction]:
        """
        Get all predictions for a match (Pro tier only)
        Returns predictions sorted by priority

        Args:
            match_id: Match identifier

        Returns:
            List of all predictions sorted by priority level (descending)
        """
        predictions = await self.db.query(Prediction).filter(
            Prediction.match_id == match_id,
            Prediction.status == PredictionStatus.PUBLISHED,
            Prediction.deleted_at == None
        ).order_by(
            Prediction.priority_level.desc(),
            Prediction.published_at.desc()
        ).all()

        return predictions

    async def _generate_randomized_prediction(self, match_id: str) -> Prediction:
        """
        Generate randomized default prediction as fallback

        Args:
            match_id: Match identifier

        Returns:
            Randomized prediction
        """
        import random

        # Generate random probabilities that sum to 1.0
        probs = [random.random() for _ in range(3)]
        total = sum(probs)
        home_win_prob = probs[0] / total
        draw_prob = probs[1] / total
        away_win_prob = probs[2] / total

        prediction = Prediction(
            match_id=match_id,
            source=PredictionSource.DEFAULT_RANDOMIZED,
            priority_level=0,
            home_win_prob=home_win_prob,
            draw_prob=draw_prob,
            away_win_prob=away_win_prob,
            confidence_score=0.0,
            status=PredictionStatus.PUBLISHED,
            reasoning="Randomized default prediction - no real data available"
        )

        return prediction
```

### 5.3 ExpertPredictionService

```python
# backend/app/services/expert_prediction.py

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.predictions import Prediction, PredictionSource, PredictionStatus
from app.models.users import User
from app.schemas.predictions import ExpertPredictionCreate, ExpertPredictionOverride

class ExpertPredictionService:
    """Service for expert prediction management"""

    def __init__(self, db: Session):
        self.db = db

    async def create_manual_prediction(
        self,
        match_id: str,
        expert_user: User,
        prediction_data: ExpertPredictionCreate
    ) -> Prediction:
        """
        Create manual expert prediction

        Args:
            match_id: Match identifier
            expert_user: Expert user creating prediction
            prediction_data: Prediction data

        Returns:
            Created prediction
        """
        prediction = Prediction(
            match_id=match_id,
            source=PredictionSource.EXPERT_MANUAL,
            priority_level=100,
            created_by=expert_user.id,
            expert_profile_id=expert_user.expert_profile.id,
            home_win_prob=prediction_data.home_win_prob,
            draw_prob=prediction_data.draw_prob,
            away_win_prob=prediction_data.away_win_prob,
            confidence_score=prediction_data.confidence_score,
            reasoning=prediction_data.reasoning,
            key_factors=prediction_data.key_factors,
            status=PredictionStatus.PENDING
        )

        self.db.add(prediction)
        await self.db.commit()
        await self.db.refresh(prediction)

        return prediction

    async def override_prediction(
        self,
        original_prediction_id: str,
        expert_user: User,
        override_data: ExpertPredictionOverride
    ) -> Prediction:
        """
        Override existing prediction (ML/LLM/API-Football)

        Args:
            original_prediction_id: ID of prediction to override
            expert_user: Expert user creating override
            override_data: Override data

        Returns:
            New expert prediction
        """
        # Get original prediction
        original = await self.db.query(Prediction).filter(
            Prediction.id == original_prediction_id
        ).first()

        if not original:
            raise ValueError(f"Prediction {original_prediction_id} not found")

        # Create new expert prediction
        new_prediction = Prediction(
            match_id=original.match_id,
            source=PredictionSource.EXPERT_OVERRIDE,
            priority_level=100,
            created_by=expert_user.id,
            expert_profile_id=expert_user.expert_profile.id,
            ml_prediction_id=original.ml_prediction_id,
            home_win_prob=override_data.home_win_prob,
            draw_prob=override_data.draw_prob,
            away_win_prob=override_data.away_win_prob,
            confidence_score=override_data.confidence_score,
            reasoning=override_data.reasoning,
            key_factors=override_data.key_factors,
            status=PredictionStatus.PENDING
        )

        self.db.add(new_prediction)
        await self.db.commit()
        await self.db.refresh(new_prediction)

        # Create override record
        from app.models.predictions import PredictionOverride
        override_record = PredictionOverride(
            prediction_id=new_prediction.id,
            expert_user_id=expert_user.id,
            expert_profile_id=expert_user.expert_profile.id,
            original_ml_prediction_id=original.id,
            original_probabilities={
                "home_win_prob": float(original.home_win_prob),
                "draw_prob": float(original.draw_prob),
                "away_win_prob": float(original.away_win_prob)
            },
            original_confidence=original.confidence_score,
            new_probabilities={
                "home_win_prob": float(new_prediction.home_win_prob),
                "draw_prob": float(new_prediction.draw_prob),
                "away_win_prob": float(new_prediction.away_win_prob)
            },
            new_confidence=new_prediction.confidence_score,
            override_reason=override_data.override_reason,
            changes_made=override_data.changes_made
        )

        self.db.add(override_record)

        # Mark original as superseded
        original.superseded_by = new_prediction.id

        await self.db.commit()

        return new_prediction

    async def get_published_prediction(self, match_id: str) -> Optional[Prediction]:
        """
        Get published expert prediction for match

        Args:
            match_id: Match identifier

        Returns:
            Expert prediction or None
        """
        prediction = await self.db.query(Prediction).filter(
            Prediction.match_id == match_id,
            Prediction.source.in_([
                PredictionSource.EXPERT_MANUAL,
                PredictionSource.EXPERT_OVERRIDE
            ]),
            Prediction.status == PredictionStatus.PUBLISHED,
            Prediction.deleted_at == None
        ).order_by(
            Prediction.published_at.desc()
        ).first()

        return prediction
```

---

## Frontend Display Strategy

### 6.1 Visual Indicators

| Source | Icon | Color | Tooltip | Tier Access |
|--------|------|-------|---------|-------------|
| **Expert** | 👤 Expert | Gold (#FFD700) | "Expert Prediction - Human Analysis" | Premium/Pro |
| **LLM** | 🤖 AI | Blue (#3B82F6) | "AI Prediction - LLM Generated" | Basic/Premium/Pro |
| **API-Football** | ⭐ API | Yellow (#FBBF24) | "API Prediction - Third-party Data" | All tiers |
| **Randomized** | 🎲 Default | Gray (#6B7280) | "Placeholder - No real data" | All tiers |

### 6.2 Display Logic

```typescript
// frontend/src/types/prediction.ts

interface PredictionDisplay {
  prediction: Prediction;
  source_indicator: {
    icon: string;
    label: string;
    color: string;
    tooltip: string;
  };
  show_confidence: boolean;  // Based on tier
  show_analysis: boolean;    // Based on tier
  show_all_sources: boolean; // Pro tier only
}

function getPredictionDisplay(
  match_id: string,
  user_tier: string
): PredictionDisplay {
  const prediction = getHighestPriorityPrediction(match_id, user_tier);

  return {
    prediction,
    source_indicator: getSourceIndicator(prediction.source),
    show_confidence: user_tier !== 'free',
    show_analysis: ['premium', 'pro'].includes(user_tier),
    show_all_sources: user_tier === 'pro'
  };
}

function getSourceIndicator(source: string) {
  const indicators = {
    'expert_manual': {
      icon: '👤',
      label: 'Expert',
      color: 'gold',
      tooltip: 'Expert Prediction - Human Analysis'
    },
    'expert_override': {
      icon: '👤',
      label: 'Expert',
      color: 'gold',
      tooltip: 'Expert Prediction - Human Analysis'
    },
    'llm_generated': {
      icon: '🤖',
      label: 'AI',
      color: 'blue',
      tooltip: 'AI Prediction - LLM Generated'
    },
    'api_football_baseline': {
      icon: '⭐',
      label: 'API',
      color: 'yellow',
      tooltip: 'API Prediction - Third-party Data'
    },
    'default_randomized': {
      icon: '🎲',
      label: 'Default',
      color: 'gray',
      tooltip: 'Placeholder - No real data'
    }
  };

  return indicators[source] || indicators['default_randomized'];
}
```

### 6.3 Multi-Source View (Pro Tier Only)

```typescript
// frontend/src/components/MultiSourcePredictionView.tsx

interface MultiSourcePredictionViewProps {
  matchId: string;
}

const MultiSourcePredictionView: React.FC<MultiSourcePredictionViewProps> = ({ matchId }) => {
  const { data: predictions } = useQuery(
    ['predictions', matchId, 'all'],
    () => predictionService.getAllPredictions(matchId)
  );

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">All Available Predictions</h3>

      {predictions?.map((prediction, index) => (
        <PredictionCard
          key={prediction.id}
          prediction={prediction}
          isActive={index === 0}  // First is highest priority
          showComparison={true}
        />
      ))}

      <PredictionComparison predictions={predictions} />
    </div>
  );
};
```

### 6.4 Prediction Card Component

```typescript
// frontend/src/components/PredictionCard.tsx

interface PredictionCardProps {
  prediction: Prediction;
  userTier: string;
  showAllSources?: boolean;
  isActive?: boolean;
}

const PredictionCard: React.FC<PredictionCardProps> = ({
  prediction,
  userTier,
  showAllSources = false,
  isActive = true
}) => {
  const sourceIndicator = getSourceIndicator(prediction.source);

  return (
    <Card className={isActive ? 'border-2 border-primary' : ''}>
      <Card.Header>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl">{sourceIndicator.icon}</span>
            <span className={`text-${sourceIndicator.color}-600 font-semibold`}>
              {sourceIndicator.label}
            </span>
            {isActive && (
              <Badge variant="success">Active</Badge>
            )}
          </div>

          {userTier !== 'free' && (
            <Badge variant={getConfidenceBadgeVariant(prediction.confidence_level)}>
              {prediction.confidence_level}% Confidence
            </Badge>
          )}
        </div>
      </Card.Header>

      <Card.Body>
        {/* Prediction probabilities */}
        <div className="grid grid-cols-3 gap-4 mb-4">
          <ProbabilityBar
            label="Home Win"
            probability={prediction.home_win_prob}
            color="green"
          />
          <ProbabilityBar
            label="Draw"
            probability={prediction.draw_prob}
            color="yellow"
          />
          <ProbabilityBar
            label="Away Win"
            probability={prediction.away_win_prob}
            color="red"
          />
        </div>

        {/* Analysis (Premium/Pro only) */}
        {['premium', 'pro'].includes(userTier) && prediction.reasoning && (
          <div className="mt-4">
            <h4 className="font-semibold mb-2">Analysis</h4>
            <p className="text-gray-700">{prediction.reasoning}</p>
          </div>
        )}

        {/* Key factors (Premium/Pro only) */}
        {['premium', 'pro'].includes(userTier) && prediction.key_factors && (
          <div className="mt-4">
            <h4 className="font-semibold mb-2">Key Factors</h4>
            <ul className="list-disc list-inside">
              {prediction.key_factors.map((factor, index) => (
                <li key={index} className="text-gray-700">{factor}</li>
              ))}
            </ul>
          </div>
        )}
      </Card.Body>
    </Card>
  );
};
```

---

## User Role Integration

### 7.1 Expert User Permissions

```python
# backend/app/core/permissions.py

class Permission(str, enum.Enum):
    """Permission enumeration"""

    # ... existing permissions ...

    # Expert Prediction Permissions
    EXPERT_VIEW_ML_BASELINE = "expert:view_ml_baseline"
    EXPERT_CREATE_MANUAL = "expert:create_manual"
    EXPERT_OVERRIDE_ML = "expert:override_ml"
    EXPERT_OVERRIDE_LLM = "expert:override_llm"
    EXPERT_OVERRIDE_API = "expert:override_api"
    EXPERT_VIEW_ANALYTICS = "expert:view_analytics"
    EXPERT_VIEW_PERFORMANCE = "expert:view_performance"
    EXPERT_COMPARE_WITH_ML = "expert:compare_ml"
    EXPERT_VIEW_ALL_SOURCES = "expert:view_all_sources"
    EXPERT_APPROVE_PREDICTION = "expert:approve_prediction"
```

### 7.2 Expert User Dependencies

```python
# backend/app/core/deps.py

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.users import User, UserType, ExpertProfile
from app.core.auth import get_current_active_user
from app.core.database import get_db

async def get_current_expert_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency to get current expert or admin user

    Checks:
    1. User is expert or admin

    Returns:
        User object

    Raises:
        HTTPException: If user is not expert or admin
    """
    if current_user.user_type not in [UserType.EXPERT, UserType.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert or Admin access required"
        )

    return current_user


async def get_current_verified_expert_user(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get current verified expert user

    Checks:
    1. User is expert or admin
    2. Expert profile exists
    3. Expert is verified
    4. Expert status is active

    Returns:
        User object

    Raises:
        HTTPException: If user is not verified expert
    """
    if current_user.user_type not in [UserType.EXPERT, UserType.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert or Admin access required"
        )

    # Admin users bypass expert verification checks
    if current_user.user_type == UserType.ADMIN:
        return current_user

    # Check expert profile
    expert_profile = db.query(ExpertProfile).filter(
        ExpertProfile.user_id == current_user.id
    ).first()

    if not expert_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert profile not found"
        )

    if not expert_profile.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert verification required. Please complete verification process."
        )

    if expert_profile.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Expert account is {expert_profile.status}. Please contact support."
        )

    return current_user


def require_permission(user: User, permission: Permission):
    """
    Check if user has specific permission

    Args:
        user: User object
        permission: Required permission

    Raises:
        HTTPException: If user doesn't have permission
    """
    # Admin users have all permissions
    if user.user_type == UserType.ADMIN:
        return

    # Check user permissions
    user_permissions = get_user_permissions(user)

    if permission not in user_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission.value}"
        )
```

### 7.3 Regular User Visibility Matrix

| User Tier | Expert Predictions | LLM Predictions | API-Football | Source Details | Multi-Source View |
|-----------|-------------------|-----------------|--------------|----------------|-------------------|
| **Free** | ❌ Hidden | ❌ Hidden | ✅ Visible | ❌ No source info | ❌ No |
| **Basic** | ❌ Hidden | ✅ Visible | ✅ Visible | ⚠️ Basic source info | ❌ No |
| **Premium** | ✅ Visible | ✅ Visible | ✅ Visible | ✅ Full source info | ❌ No |
| **Pro** | ✅ Visible | ✅ Visible | ✅ Visible | ✅ Full source info | ✅ Yes |

**Display Strategy**:
- **Free tier**: Show prediction without source attribution
- **Basic tier**: Show source icon (🤖 or ⭐) but not expert predictions
- **Premium tier**: Show all predictions with source attribution
- **Pro tier**: Show all predictions + comparison view + analytics

---

## API Integration Points

### 8.1 Expert Prediction Endpoints (KAN-26)

#### POST /api/v1/expert/predictions/manual

Create manual expert prediction from scratch.

**Request**:
```json
{
  "match_id": "uuid",
  "home_win_prob": 0.45,
  "draw_prob": 0.25,
  "away_win_prob": 0.30,
  "confidence_score": 0.85,
  "reasoning": "Liverpool's injury crisis favors United...",
  "key_factors": [
    "Liverpool missing 3 key defenders",
    "United's home form excellent (8W-1D-1L)",
    "Head-to-head favors United at Old Trafford"
  ]
}
```

**Response**:
```json
{
  "id": "uuid",
  "match_id": "uuid",
  "source": "expert_manual",
  "priority_level": 100,
  "status": "pending_review",
  "home_win_prob": 0.45,
  "draw_prob": 0.25,
  "away_win_prob": 0.30,
  "confidence_score": 0.85,
  "reasoning": "Liverpool's injury crisis favors United...",
  "created_at": "2025-10-12T10:00:00Z"
}
```

#### POST /api/v1/expert/predictions/{id}/override

Override existing prediction (ML/LLM/API-Football).

**Request**:
```json
{
  "home_win_prob": 0.50,
  "draw_prob": 0.20,
  "away_win_prob": 0.30,
  "confidence_score": 0.90,
  "reasoning": "ML model underestimates United's home advantage",
  "override_reason": "ML model doesn't account for recent injuries",
  "changes_made": {
    "home_win_prob": {
      "from": 0.40,
      "to": 0.50,
      "reason": "Increased due to Liverpool injuries"
    }
  }
}
```

**Response**:
```json
{
  "id": "uuid",
  "match_id": "uuid",
  "source": "expert_override",
  "priority_level": 100,
  "status": "pending_review",
  "original_prediction_id": "uuid",
  "override_details": {
    "original_probabilities": {
      "home_win_prob": 0.40,
      "draw_prob": 0.30,
      "away_win_prob": 0.30
    },
    "new_probabilities": {
      "home_win_prob": 0.50,
      "draw_prob": 0.20,
      "away_win_prob": 0.30
    }
  },
  "created_at": "2025-10-12T10:00:00Z"
}
```

#### GET /api/v1/expert/predictions/review-queue

Get predictions flagged for expert review.

**Query Parameters**:
- `confidence_threshold`: Filter by confidence < threshold (default: 0.7)
- `league_id`: Filter by league specialization
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20)

**Response**:
```json
{
  "predictions": [
    {
      "id": "uuid",
      "match_id": "uuid",
      "match_details": {
        "home_team": "Manchester United",
        "away_team": "Liverpool",
        "league": "Premier League",
        "match_date": "2025-10-15T15:00:00Z"
      },
      "ml_prediction": {
        "home_win_prob": 0.40,
        "draw_prob": 0.30,
        "away_win_prob": 0.30,
        "confidence_score": 0.65
      },
      "flagged_reason": "Low confidence score",
      "expert_specialization_match": true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 45,
    "total_pages": 3
  }
}
```

#### GET /api/v1/expert/predictions/my-predictions

Get expert's own predictions with performance metrics.

**Query Parameters**:
- `status`: Filter by status (pending, approved, published, etc.)
- `date_from`: Start date
- `date_to`: End date
- `page`: Page number
- `page_size`: Items per page

**Response**:
```json
{
  "predictions": [
    {
      "id": "uuid",
      "match_id": "uuid",
      "source": "expert_manual",
      "status": "published",
      "outcome": "won",
      "accuracy_contribution": 0.92,
      "created_at": "2025-10-12T10:00:00Z",
      "published_at": "2025-10-12T12:00:00Z"
    }
  ],
  "performance_summary": {
    "total_predictions": 150,
    "accuracy_rate": 0.73,
    "win_rate": 0.68,
    "average_confidence": 0.82
  },
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 150,
    "total_pages": 8
  }
}
```

#### GET /api/v1/expert/analytics/performance

Get expert performance metrics and analytics.

**Response**:
```json
{
  "expert_id": "uuid",
  "verification_level": 7,
  "overall_performance": {
    "total_predictions": 150,
    "accuracy_rate": 0.73,
    "win_rate": 0.68,
    "average_confidence": 0.82,
    "roi": 0.15
  },
  "performance_by_league": [
    {
      "league_id": "uuid",
      "league_name": "Premier League",
      "predictions_count": 80,
      "accuracy_rate": 0.78,
      "specialization": true
    }
  ],
  "performance_by_market": [
    {
      "market_type": "match_result",
      "predictions_count": 120,
      "accuracy_rate": 0.75
    }
  ],
  "recent_trend": {
    "last_30_days": {
      "predictions_count": 25,
      "accuracy_rate": 0.80
    },
    "trend": "improving"
  }
}
```

### 8.2 Unified Prediction Retrieval Endpoints

#### GET /api/v1/predictions/{match_id}

Get highest priority prediction for match (tier-based).

**Query Parameters**:
- `include_all_sources`: Boolean (Pro tier only, default: false)

**Response (Single Prediction)**:
```json
{
  "match_id": "uuid",
  "prediction": {
    "id": "uuid",
    "source": "expert_manual",
    "priority_level": 100,
    "home_win_prob": 0.45,
    "draw_prob": 0.25,
    "away_win_prob": 0.30,
    "confidence_score": 0.85,
    "reasoning": "Liverpool's injury crisis favors United...",
    "created_at": "2025-10-12T10:00:00Z"
  },
  "source_indicator": {
    "icon": "👤",
    "label": "Expert",
    "color": "gold",
    "tooltip": "Expert Prediction - Human Analysis"
  }
}
```

**Response (All Sources - Pro Tier)**:
```json
{
  "match_id": "uuid",
  "predictions": [
    {
      "id": "uuid",
      "source": "expert_manual",
      "priority_level": 100,
      "home_win_prob": 0.45,
      "draw_prob": 0.25,
      "away_win_prob": 0.30,
      "confidence_score": 0.85,
      "is_active": true
    },
    {
      "id": "uuid",
      "source": "llm_generated",
      "priority_level": 50,
      "home_win_prob": 0.40,
      "draw_prob": 0.30,
      "away_win_prob": 0.30,
      "confidence_score": 0.78,
      "is_active": false
    },
    {
      "id": "uuid",
      "source": "api_football_baseline",
      "priority_level": 25,
      "home_win_prob": 0.38,
      "draw_prob": 0.28,
      "away_win_prob": 0.34,
      "confidence_score": 0.65,
      "is_active": false
    }
  ],
  "active_prediction": {
    "id": "uuid",
    "source": "expert_manual"
  }
}
```

#### GET /api/v1/predictions/today

Get today's predictions with priority logic applied.

**Query Parameters**:
- `sort_by`: Sort field (confidence, created_at, match_time)
- `page`: Page number
- `page_size`: Items per page

**Response**:
```json
{
  "predictions": [
    {
      "id": "uuid",
      "match_id": "uuid",
      "match_details": {
        "home_team": "Manchester United",
        "away_team": "Liverpool",
        "league": "Premier League",
        "match_date": "2025-10-12T15:00:00Z"
      },
      "source": "expert_manual",
      "priority_level": 100,
      "home_win_prob": 0.45,
      "draw_prob": 0.25,
      "away_win_prob": 0.30,
      "confidence_score": 0.85
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 15,
    "total_pages": 1
  },
  "tier_info": {
    "tier": "premium",
    "access_level": "expert_predictions"
  }
}
```

### 8.3 Recommendation: Unified vs Separate Endpoints

**Recommendation**: **Single unified `/predictions/{match_id}` endpoint** with priority logic.

**Rationale**:
- ✅ **Simplicity**: Frontend only needs one endpoint
- ✅ **Consistency**: Priority logic handled server-side
- ✅ **Tier-based filtering**: Automatic based on user's subscription
- ✅ **Flexibility**: `include_all_sources` parameter for Pro tier
- ✅ **Caching**: Easier to cache single endpoint

**Alternative (Rejected)**: Separate endpoints per source
- `/predictions/{match_id}/expert`
- `/predictions/{match_id}/llm`
- `/predictions/{match_id}/api-football`

**Why Rejected**:
- ❌ More complex frontend logic
- ❌ Multiple API calls required
- ❌ Priority logic must be implemented client-side
- ❌ More difficult to cache effectively

---

## Audit Trail & Logging

### 9.1 Audit Trail Requirements

**What to Track**:
1. **Prediction Creation**: Who created, when, source type, priority level
2. **Prediction Selection**: Which prediction was shown to user, why (priority logic)
3. **Prediction Override**: Original vs. new values, expert reasoning
4. **Prediction Updates**: All field changes with before/after values
5. **Prediction Status Changes**: pending → approved → published → settled
6. **Prediction Voiding**: Who voided, when, reason

### 9.2 PredictionAudit Model

```python
# backend/app/models/predictions.py

class PredictionAudit(Base, UUIDMixin, TimestampMixin):
    """Comprehensive audit trail for predictions"""
    __tablename__ = "prediction_audit"
    __table_args__ = (
        Index('idx_prediction_audit_prediction_id', 'prediction_id'),
        Index('idx_prediction_audit_actor_id', 'actor_id'),
        Index('idx_prediction_audit_action_type', 'action_type'),
        Index('idx_prediction_audit_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction audit trail'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    action_type = Column(String(50), nullable=False)  # created, updated, overridden, selected, voided
    actor_type = Column(String(50), nullable=False)  # ml_system, llm_system, expert_user, admin_user, system
    actor_id = uuid_fk('users.users.id', nullable=True)  # User ID if applicable

    # Action Details
    action_details = Column(JSONB, comment="Detailed action context")
    changes_made = Column(JSONB, comment="Before/after values")
    selection_reason = Column(Text, comment="Why this prediction was selected")

    # Request Context
    ip_address = Column(INET, comment="IP address of request")
    user_agent = Column(Text, comment="User agent string")
    request_id = Column(String(100), comment="Request tracking ID")
```

### 9.3 PredictionAuditService

```python
# backend/app/services/prediction_audit.py

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.predictions import PredictionAudit, Prediction
from app.models.users import User

class PredictionAuditService:
    """Service for comprehensive prediction audit logging"""

    def __init__(self, db: Session):
        self.db = db

    async def log_prediction_created(
        self,
        prediction: Prediction,
        creator: User,
        context: Dict[str, Any]
    ):
        """Log prediction creation"""
        audit_log = PredictionAudit(
            prediction_id=prediction.id,
            action_type="created",
            actor_type=self._get_actor_type(creator),
            actor_id=creator.id,
            action_details={
                "source": prediction.source,
                "priority_level": prediction.priority_level,
                "match_id": str(prediction.match_id),
                "confidence_score": float(prediction.confidence_score),
                **context
            },
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            request_id=context.get("request_id")
        )
        self.db.add(audit_log)
        await self.db.commit()

    async def log_prediction_selected(
        self,
        prediction: Prediction,
        selection_reason: str,
        alternatives: List[Prediction] = None,
        user: User = None
    ):
        """Log prediction selection (which prediction shown to user)"""
        audit_log = PredictionAudit(
            prediction_id=prediction.id,
            action_type="selected",
            actor_type="system",
            action_details={
                "user_id": str(user.id) if user else None,
                "user_tier": user.subscription_tier if user else None,
                "selection_reason": selection_reason,
                "priority_level": prediction.priority_level,
                "alternatives": [
                    {
                        "id": str(alt.id),
                        "source": alt.source,
                        "priority": alt.priority_level
                    }
                    for alt in (alternatives or [])
                ]
            },
            selection_reason=selection_reason
        )
        self.db.add(audit_log)
        await self.db.commit()

    async def log_prediction_override(
        self,
        prediction: Prediction,
        expert: User,
        original_prediction: Prediction,
        override_reason: str,
        changes: Dict[str, Any]
    ):
        """Log expert override of prediction"""
        audit_log = PredictionAudit(
            prediction_id=prediction.id,
            action_type="overridden",
            actor_type="expert_user",
            actor_id=expert.id,
            action_details={
                "original_prediction_id": str(original_prediction.id),
                "original_source": original_prediction.source,
                "override_reason": override_reason,
                "expert_profile_id": str(expert.expert_profile.id) if expert.expert_profile else None
            },
            changes_made={
                "before": {
                    "home_win_prob": float(original_prediction.home_win_prob),
                    "draw_prob": float(original_prediction.draw_prob),
                    "away_win_prob": float(original_prediction.away_win_prob),
                    "confidence_score": float(original_prediction.confidence_score)
                },
                "after": {
                    "home_win_prob": float(prediction.home_win_prob),
                    "draw_prob": float(prediction.draw_prob),
                    "away_win_prob": float(prediction.away_win_prob),
                    "confidence_score": float(prediction.confidence_score)
                },
                **changes
            }
        )
        self.db.add(audit_log)
        await self.db.commit()

    def _get_actor_type(self, user: User) -> str:
        """Determine actor type from user"""
        from app.models.users import UserType

        if user.user_type == UserType.EXPERT:
            return "expert_user"
        elif user.user_type == UserType.ADMIN:
            return "admin_user"
        else:
            return "regular_user"
```

---

## Caching Strategy

### 10.1 Cache Key Structure

```
# User-specific prediction (tier-based)
prediction:{match_id}:{user_tier}

# All predictions for match (Pro tier)
prediction:all:{match_id}

# Source-specific predictions
prediction:expert:{match_id}
prediction:llm:{match_id}
prediction:api:{match_id}

# Expert review queue
expert:review_queue:{expert_id}:{page}

# Expert performance metrics
expert:performance:{expert_id}
```

### 10.2 Cache TTL Strategy

| Cache Type | Before Match | During Match | After Match | Rationale |
|------------|--------------|--------------|-------------|-----------|
| **Expert Prediction** | 5 minutes | 1 minute | 1 hour | May be updated before match |
| **LLM Prediction** | 10 minutes | 2 minutes | 1 hour | Less frequent updates |
| **API-Football** | 15 minutes | 5 minutes | 2 hours | External API, rate limits |
| **Aggregated Prediction** | 5 minutes | 1 minute | 1 hour | Follows highest priority source |
| **Review Queue** | 10 minutes | N/A | N/A | Changes when predictions created |
| **Performance Metrics** | 1 hour | N/A | 1 hour | Infrequent updates |

### 10.3 Cache Invalidation Events

**When to Invalidate**:
1. **Expert creates/updates prediction** → Invalidate expert cache, aggregated cache
2. **LLM generates new prediction** → Invalidate LLM cache, aggregated cache
3. **Prediction status changes** → Invalidate all related caches
4. **Match starts** → Reduce TTL to 1 minute
5. **Match ends** → Invalidate all match-related caches, increase TTL to 1 hour
6. **Prediction voided** → Invalidate all related caches

**Implementation**:
```python
# backend/app/services/prediction_cache.py

class PredictionCacheInvalidator:
    """Handles cache invalidation for prediction updates"""

    def __init__(self, cache: RedisClient):
        self.cache = cache

    async def invalidate_prediction_caches(
        self,
        match_id: str,
        source: str = None
    ):
        """
        Invalidate all caches related to a prediction

        Args:
            match_id: Match identifier
            source: Prediction source (optional, invalidates specific source)
        """
        # Invalidate aggregated caches for all tiers
        for tier in ['free', 'basic', 'premium', 'pro']:
            await self.cache.delete(f"prediction:{match_id}:{tier}")

        # Invalidate all sources cache
        await self.cache.delete(f"prediction:all:{match_id}")

        # Invalidate source-specific cache if provided
        if source:
            source_key_map = {
                'expert_manual': f"prediction:expert:{match_id}",
                'expert_override': f"prediction:expert:{match_id}",
                'llm_generated': f"prediction:llm:{match_id}",
                'api_football_baseline': f"prediction:api:{match_id}"
            }
            if source in source_key_map:
                await self.cache.delete(source_key_map[source])

    async def invalidate_expert_caches(self, expert_id: str):
        """Invalidate expert-specific caches"""
        # Invalidate review queue
        pattern = f"expert:review_queue:{expert_id}:*"
        await self.cache.delete_pattern(pattern)

        # Invalidate performance metrics
        await self.cache.delete(f"expert:performance:{expert_id}")
```

### 10.4 Redis Database Allocation

```python
# backend/app/core/config.py

class Settings(BaseSettings):
    # Redis database allocation
    REDIS_DB_SESSIONS = 0          # User sessions, JWT blacklist
    REDIS_DB_PREDICTIONS = 1       # Prediction caching
    REDIS_DB_EXPERT_TOOLS = 2      # Expert review queue, performance metrics
    REDIS_DB_ML_CACHE = 3          # ML model predictions
    REDIS_DB_RATE_LIMITING = 4     # API rate limiting
```

---

## Recommendations & Implementation Approach

### 11.1 Prediction Priority Logic

**Recommendation**: **Waterfall/Cascade Logic** with tier-based filtering.

**Pros**:
- ✅ Simple to understand and implement
- ✅ Clear priority hierarchy
- ✅ Easy to add new sources in future
- ✅ Supports tier-based access control
- ✅ Graceful fallback to lower priority sources

**Cons**:
- ⚠️ May hide valuable alternative predictions from users (mitigated by Pro tier multi-source view)
- ⚠️ Requires careful cache invalidation

**Alternative Considered**: **Ensemble/Weighted Average**
- Combine predictions from multiple sources with weights
- **Rejected**: Too complex for initial implementation, harder to explain to users, less transparent

### 11.2 Data Model & Storage

**Recommendation**: **Store ALL predictions** with `priority_level` field.

**Implementation Steps**:
1. Add `priority_level` INTEGER field to `predictions.predictions` table
2. Add `superseded_by` UUID field to track prediction supersession
3. Update `PredictionSource` enum to include LLM and API-Football sources
4. Create composite index on `(match_id, priority_level DESC, published_at DESC)`
5. Update existing predictions with priority levels based on source

**Benefits**:
- ✅ Complete audit trail
- ✅ A/B testing capabilities
- ✅ Fallback options if higher priority prediction voided
- ✅ Analytics on source performance
- ✅ Transparency for Pro tier users

### 11.3 Service Layer Architecture

**Recommendation**: **Create new `PredictionAggregatorService`** as central orchestrator.

**Architecture**:
```
PredictionAggregatorService (NEW)
├── ExpertPredictionService (NEW)
├── LLMPredictionService (NEW - Future)
├── APIFootballPredictionService (NEW)
└── PredictionCacheService (Existing)
```

**Benefits**:
- ✅ Single source of truth for prediction retrieval
- ✅ Encapsulates priority logic
- ✅ Easy to test and maintain
- ✅ Supports future sources (e.g., user predictions, betting odds)
- ✅ Separation of concerns

### 11.4 Frontend Display Strategy

**Recommendation**: **Tiered visibility** with clear visual indicators.

**Implementation**:
1. **Free tier**: Show prediction without source details
2. **Basic tier**: Show source icon (🤖 LLM or ⭐ API)
3. **Premium tier**: Show source icon + expert predictions (👤)
4. **Pro tier**: Show all sources + comparison view

**Visual Indicators**:
- 👤 Expert (Gold) - Premium/Pro only
- 🤖 AI (Blue) - Basic/Premium/Pro
- ⭐ API (Yellow) - All tiers
- 🎲 Default (Gray) - All tiers

### 11.5 User Role Integration

**Recommendation**: **Extend existing RBAC system** with expert-specific permissions.

**Implementation**:
1. Add expert permissions to `Permission` enum
2. Create `@require_expert` decorator for expert endpoints
3. Implement expert verification check in dependencies
4. Add tier-based filtering in prediction retrieval

**Expert Permissions**:
- `expert:view_ml_baseline`
- `expert:create_manual`
- `expert:override_ml`
- `expert:override_llm`
- `expert:override_api`
- `expert:view_analytics`

### 11.6 Audit Trail

**Recommendation**: **Comprehensive logging** of all prediction lifecycle events.

**What to Log**:
1. Prediction creation (source, priority, creator)
2. Prediction selection (which prediction shown to user, why)
3. Prediction override (original vs. new, expert reasoning)
4. Prediction status changes (pending → approved → published)
5. Prediction voiding (who, when, reason)

**Implementation**: Use `PredictionAuditService` with JSONB fields for flexible logging.

---

## Risks & Mitigation

### 12.1 Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Cache invalidation complexity** | High | Medium | Event-driven invalidation with Redis pub/sub, comprehensive testing |
| **Database performance** | High | Low | Composite indexes, query optimization, read replicas for analytics |
| **Priority logic bugs** | High | Medium | Comprehensive unit tests, integration tests, manual QA |
| **LLM integration delays** | Medium | High | Async processing, fallback to API-Football, timeout handling |
| **API-Football quota limits** | Medium | Medium | Aggressive caching (15min TTL), rate limiting, quota monitoring |
| **Race conditions** | Medium | Low | Database transactions, optimistic locking, idempotency keys |

### 12.2 Business Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Expert prediction quality** | High | Medium | Performance monitoring, minimum accuracy requirements (70%+), suspension for poor performance |
| **User confusion (multiple sources)** | Medium | High | Clear visual indicators, tooltips, help documentation, onboarding |
| **Tier cannibalization** | Medium | Low | Ensure clear value proposition for each tier, feature differentiation |
| **Expert churn** | Medium | Medium | Gamification, leaderboards, recognition, potential monetization (revenue share) |
| **Legal/compliance** | High | Low | Terms of service, disclaimers, responsible gambling messaging |

### 12.3 Data Integrity Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Probability sum != 1.0** | High | Low | Database CHECK constraint, Pydantic validation, frontend validation |
| **Orphaned predictions** | Medium | Low | Foreign key constraints, cascade deletes, periodic cleanup jobs |
| **Audit trail gaps** | High | Low | Comprehensive logging, automated tests, monitoring alerts |
| **Prediction conflicts** | Medium | Medium | Priority-based resolution, status tracking, superseded_by field |
| **Data loss** | High | Low | Database backups (daily), point-in-time recovery, replication |

### 12.4 Performance Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **Slow prediction retrieval** | High | Medium | Caching (5min TTL), database indexes, query optimization |
| **High database load** | High | Low | Connection pooling, read replicas, query optimization |
| **Redis memory exhaustion** | Medium | Low | TTL-based expiration, memory limits, eviction policies |
| **API timeout** | Medium | Medium | Async processing, timeout handling (5s), circuit breakers |

---

## Implementation Roadmap

### 13.1 Phase 1: Foundation (Week 1-2)

**Prerequisites**:
1. ✅ Complete KAN-24 (RBAC system) - **BLOCKER**
2. ✅ Complete KAN-33 (ML models) - **BLOCKER**
3. ✅ Complete KAN-139 (Subscription tier middleware)

**Tasks**:
1. Database schema migration
   - Add `priority_level` field
   - Add `superseded_by` field
   - Update `PredictionSource` enum
   - Create composite indexes
   - Update existing predictions with priority levels

2. Create `PredictionAggregatorService`
   - Implement waterfall priority logic
   - Add tier-based filtering
   - Integrate with caching layer

3. Add expert permissions to RBAC
   - Update `Permission` enum
   - Create expert dependencies
   - Implement permission checks

**Deliverables**:
- ✅ Database migration script
- ✅ `PredictionAggregatorService` implementation
- ✅ Expert permissions in RBAC
- ✅ Unit tests (>80% coverage)

### 13.2 Phase 2: Expert API Endpoints (Week 3-4) - **KAN-26**

**Tasks**:
1. Implement `POST /expert/predictions/manual`
   - Request validation (Pydantic schemas)
   - Expert verification check
   - Prediction creation logic
   - Audit logging

2. Implement `POST /expert/predictions/{id}/override`
   - Original prediction retrieval
   - Override validation
   - Override record creation
   - Supersession tracking
   - Audit logging

3. Implement `GET /expert/predictions/review-queue`
   - Confidence threshold filtering
   - League specialization matching
   - Pagination support
   - Caching (10min TTL)

4. Implement `GET /expert/predictions/my-predictions`
   - Status filtering
   - Date range filtering
   - Performance metrics calculation
   - Pagination support

5. Implement `GET /expert/analytics/performance`
   - Overall performance metrics
   - Performance by league
   - Performance by market
   - Recent trend analysis
   - Caching (1hr TTL)

6. Add comprehensive audit logging
   - Prediction creation logs
   - Prediction override logs
   - Prediction selection logs

7. Write unit tests
   - Service layer tests
   - API endpoint tests
   - Permission tests
   - >80% code coverage

**Deliverables**:
- ✅ 5 Expert API endpoints implemented
- ✅ `ExpertPredictionService` implementation
- ✅ `PredictionAuditService` implementation
- ✅ Comprehensive unit tests
- ✅ API documentation (OpenAPI)

### 13.3 Phase 3: LLM Integration (Week 5-6) - **Future**

**Tasks**:
1. Create `LLMPredictionService`
2. Implement LLM prediction generation (async)
3. Add LLM predictions to priority logic
4. Update frontend to display LLM predictions

**Deliverables**:
- ✅ `LLMPredictionService` implementation
- ✅ LLM prediction generation
- ✅ Integration with aggregator service

### 13.4 Phase 4: Frontend Integration (Week 7-8)

**Tasks**:
1. Update prediction display components
   - Add source indicators (👤, 🤖, ⭐)
   - Implement tier-based visibility
   - Add confidence badges

2. Implement multi-source view (Pro tier)
   - All sources display
   - Comparison view
   - Active prediction highlighting

3. Update API client
   - Add expert prediction endpoints
   - Add unified prediction retrieval
   - Handle tier-based responses

4. Add tier-based filtering
   - Free tier: No source info
   - Basic tier: LLM + API
   - Premium tier: Expert + LLM + API
   - Pro tier: All sources + comparison

**Deliverables**:
- ✅ Updated prediction components
- ✅ Multi-source view (Pro tier)
- ✅ Updated API client
- ✅ Tier-based filtering

### 13.5 Phase 5: Testing & Optimization (Week 9-10)

**Tasks**:
1. Integration testing
   - End-to-end prediction flow
   - Multi-source priority logic
   - Tier-based access control

2. Performance testing
   - Load testing (1000 concurrent users)
   - Cache hit rate optimization
   - Query optimization

3. User acceptance testing
   - Expert user testing
   - Regular user testing
   - Admin user testing

4. Documentation updates
   - API documentation
   - User guides
   - Admin guides

5. Production deployment
   - Database migration
   - Backend deployment
   - Frontend deployment
   - Monitoring setup

**Deliverables**:
- ✅ Integration test suite
- ✅ Performance test results
- ✅ UAT sign-off
- ✅ Complete documentation
- ✅ Production deployment

---

## Success Metrics

### 14.1 Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **API Response Time** | <500ms (P95) | CloudWatch metrics |
| **Cache Hit Rate** | >80% | Redis metrics |
| **Database Query Time** | <100ms (P95) | PostgreSQL slow query log |
| **Prediction Retrieval Accuracy** | >99% | Audit logs |
| **Zero Data Integrity Violations** | 100% | Database constraints |
| **Test Coverage** | >80% | pytest coverage report |

### 14.2 Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Expert Prediction Accuracy** | >70% | Prediction results analysis |
| **Expert Retention Rate** | >80% | Monthly active experts |
| **User Engagement** | +20% | Prediction views, feedback |
| **Premium Tier Conversion** | +15% | Subscription upgrades |
| **Expert Predictions per Week** | 50+ | Prediction creation logs |

### 14.3 Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Audit Trail Completeness** | 100% | Audit log coverage |
| **Priority Logic Correctness** | >99% | Automated tests |
| **Expert Verification Rate** | >95% | Expert profile status |
| **Prediction Approval Time** | <24 hours | Status change logs |
| **User Satisfaction** | >4.0/5.0 | User feedback surveys |

---

## Appendices

### Appendix A: KAN-26 Endpoint Summary

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `/expert/predictions/manual` | POST | Create manual prediction | High |
| `/expert/predictions/{id}/override` | POST | Override existing prediction | High |
| `/expert/predictions/review-queue` | GET | Get predictions for review | High |
| `/expert/predictions/my-predictions` | GET | Get expert's predictions | Medium |
| `/expert/analytics/performance` | GET | Get performance metrics | Medium |
| `/expert/analytics/accuracy` | GET | Get accuracy tracking | Low |
| `/expert/predictions/{id}/approve` | PUT | Approve prediction | Low |

### Appendix B: Database Schema Changes

```sql
-- Add priority_level field
ALTER TABLE predictions.predictions
ADD COLUMN priority_level INTEGER DEFAULT 0
CHECK (priority_level >= 0 AND priority_level <= 100);

-- Add superseded_by field
ALTER TABLE predictions.predictions
ADD COLUMN superseded_by UUID REFERENCES predictions.predictions(id);

-- Create composite index
CREATE INDEX idx_predictions_priority
ON predictions.predictions(match_id, priority_level DESC, published_at DESC)
WHERE status = 'published' AND deleted_at IS NULL;

-- Update existing predictions
UPDATE predictions.predictions
SET priority_level = CASE source
    WHEN 'expert_manual' THEN 100
    WHEN 'expert_override' THEN 100
    WHEN 'admin_manual' THEN 100
    WHEN 'ml_baseline' THEN 40
    ELSE 0
END;

-- Add new enum values
ALTER TYPE predictions.prediction_source ADD VALUE IF NOT EXISTS 'llm_generated';
ALTER TYPE predictions.prediction_source ADD VALUE IF NOT EXISTS 'api_football_baseline';
ALTER TYPE predictions.prediction_source ADD VALUE IF NOT EXISTS 'default_randomized';
```

### Appendix C: Priority Level Reference

| Source | Priority Level | Tier Access | Description |
|--------|---------------|-------------|-------------|
| `expert_manual` | 100 | Premium/Pro | Manual expert prediction |
| `expert_override` | 100 | Premium/Pro | Expert override of ML/LLM/API |
| `admin_manual` | 100 | Premium/Pro | Admin manual prediction |
| `llm_generated` | 50 | Basic/Premium/Pro | LLM-generated prediction |
| `ml_baseline` | 40 | Basic/Premium/Pro | Legacy ML prediction |
| `api_football_baseline` | 25 | All tiers | API-Football prediction |
| `default_randomized` | 0 | All tiers | Fallback randomized |

### Appendix D: Glossary

- **Waterfall Logic**: Sequential priority-based selection where highest priority source is selected first
- **Tier-based Filtering**: Access control based on user's subscription tier
- **Supersession**: When a higher priority prediction replaces a lower priority one
- **Audit Trail**: Complete log of all prediction lifecycle events
- **Priority Level**: Numeric value (0-100) indicating prediction source priority
- **Expert Verification**: Process of validating expert user credentials and performance
- **Prediction Aggregator**: Service that orchestrates multi-source prediction retrieval

---

## Conclusion

The multi-source prediction priority system is a **complex but well-architected solution** that will enable the Soccer Predictions Platform to deliver high-quality predictions from multiple sources while maintaining data integrity, audit trails, and user experience.

**Key Takeaways**:

1. **Waterfall priority logic** provides simple, transparent prediction selection
2. **Store ALL predictions** for complete audit trail and analytics
3. **PredictionAggregatorService** centralizes priority logic and caching
4. **Tier-based visibility** ensures appropriate access control
5. **Comprehensive audit logging** tracks all prediction lifecycle events
6. **Expert API endpoints (KAN-26)** enable the hybrid prediction system

**Critical Path**:
1. Complete KAN-24 (RBAC) and KAN-33 (ML models) first
2. Implement database schema changes
3. Build `PredictionAggregatorService`
4. Implement Expert API endpoints (KAN-26)
5. Integrate LLM predictions (future)
6. Update frontend

**Next Steps**:
1. Review and approve this analysis document
2. Complete blocking dependencies (KAN-24, KAN-33)
3. Begin Phase 1: Foundation (database migration, aggregator service)
4. Implement Phase 2: Expert API endpoints (KAN-26)
5. Test and deploy to production

This analysis provides a solid foundation for implementing KAN-26 and the broader multi-source prediction priority system. The architecture is scalable, maintainable, and aligned with the project's long-term vision.

---

**Document Status**: ✅ Analysis Complete - Ready for Implementation Planning
**Last Updated**: 2025-10-12
**Version**: 1.0
**Author**: Augment Code (Co-authored by Steph)
**Jira Task**: [KAN-26](https://aztechsolutions.atlassian.net/browse/KAN-26)

---

*This document is part of the Soccer Predictions Platform technical documentation. For questions or clarifications, please contact the development team.*

