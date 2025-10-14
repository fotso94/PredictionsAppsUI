# KAN-26: Storage & Tracking - Brief Summary

**Date**: 2025-10-12 | **Status**: ✅ Recommendations Ready

## Storage Strategy (REVISED)

**DECISION**: Store ONLY Expert and LLM predictions in database. Access API-Football via API/cache.

- **Expert Predictions**: Store in PostgreSQL (3-year retention) - High value, audit trail, performance tracking
- **LLM Predictions**: Store in PostgreSQL (2-year retention) - ML training, A/B testing
- **API-Football**: Cache in Redis (15min TTL), fetch from API on-demand - No DB storage needed

**Benefits**: 67% storage reduction (27GB vs 81GB), $11/month savings, simpler management, maintains audit trail.

## User Tracking Strategy

**DECISION**: Create `analytics.prediction_source_views` table to track which predictions users see.

**Key Metrics**: Views by source (Expert/LLM/API), views by tier, engagement rate, tier conversion after viewing expert predictions.

**Implementation**: Track in analytics schema, 1-year retention, use data to optimize prediction generation.

---

**Full Analysis**: See `KAN-26_STORAGE_AND_TRACKING_RECOMMENDATIONS.md` for detailed implementation.

