# ML Models Schema - Quick Reference Summary
## Soccer Predictions Platform

**Jira Task**: KAN-94  
**Status**: ✅ Complete - Ready for Review  
**Last Updated**: 2025-10-08

---

## Schema Overview

The **ml_models** schema contains **12 tables** organized into 4 functional groups:

| Group | Tables | Purpose |
|-------|--------|---------|
| **Core Models** | 2 tables | Models registry, features registry |
| **Training Pipeline** | 4 tables | Training runs, metrics, feature importance, engineering |
| **Predictions & Explanations** | 2 tables | ML predictions, explanations (SHAP, LIME) |
| **Deployment & Testing** | 4 tables | Performance, deployments, A/B tests, test results |

---

## Table Summary

### Core Model Tables (2 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 1 | `ml_models` | 50-100 | Model registry with versioning | → training_runs, predictions, performance, deployments |
| 2 | `ml_features` | 200-500 | Feature registry and metadata | → feature_importance, feature_engineering |

### Training Pipeline Tables (4 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 3 | `ml_training_runs` | 500-1K | Training run history | ← ml_models (1:many) |
| 4 | `ml_training_metrics` | 50K-100K | Epoch-level metrics | ← ml_training_runs (1:many) |
| 5 | `ml_feature_importance` | 50K-100K | Feature importance scores | ← ml_training_runs, ml_features |
| 6 | `ml_feature_engineering` | 1K-2K | Feature engineering versions | ← ml_features (1:many) |

### Predictions & Explanations Tables (2 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 7 | `ml_predictions` | 500K+ | Raw ML predictions | ← ml_models, matches |
| 8 | `ml_prediction_explanations` | 500K+ | Explainability data (SHAP, LIME) | ← ml_predictions (1:many) |

### Deployment & Testing Tables (4 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 9 | `ml_model_performance` | 5K-10K | Performance metrics snapshots | ← ml_models (1:many) |
| 10 | `ml_model_deployments` | 200-500 | Deployment history | ← ml_models (1:many) |
| 11 | `ml_ab_tests` | 50-100 | A/B test definitions | → ml_models (champion, challenger) |
| 12 | `ml_ab_test_results` | 1K-2K | A/B test results over time | ← ml_ab_tests (1:many) |

---

## Key Features

### 🤖 ML Model Management
- ✅ Semantic versioning (e.g., 1.2.3)
- ✅ Model lifecycle (development → testing → staging → production → deprecated)
- ✅ Multiple model types (random_forest, xgboost, neural_network, ensemble)
- ✅ Framework tracking (scikit-learn, tensorflow, pytorch)
- ✅ S3 artifact storage with versioning
- ✅ Champion model designation

### 🔬 Training Pipeline
- ✅ Complete training run history
- ✅ Hyperparameter tracking
- ✅ Dataset configuration and lineage
- ✅ Epoch-level metrics (loss, accuracy)
- ✅ Training duration and resource usage
- ✅ Error logging for failed runs

### 📊 Model Performance
- ✅ Accuracy, precision, recall, F1 score
- ✅ AUC-ROC, log loss, Brier score
- ✅ Confusion matrix
- ✅ Performance by market, league, confidence
- ✅ Calibration error tracking
- ✅ Time-series performance monitoring

### 🚀 Deployment Management
- ✅ Multi-environment (development, staging, production)
- ✅ Deployment strategies (blue_green, canary, rolling)
- ✅ Traffic splitting for canary deployments
- ✅ Latency monitoring (avg, p95, p99)
- ✅ Rollback capability with reasoning
- ✅ Endpoint URL tracking

### 🔍 Model Explainability
- ✅ SHAP values
- ✅ LIME explanations
- ✅ Feature importance
- ✅ Attention weights (for neural networks)
- ✅ Human-readable explanations
- ✅ Top contributing features

### 🧪 A/B Testing
- ✅ Champion vs Challenger paradigm
- ✅ Traffic splitting (0-100%)
- ✅ Statistical significance testing
- ✅ Minimum sample size requirements
- ✅ Time-series result tracking
- ✅ Automated winner determination

### 🔧 Feature Engineering
- ✅ Central feature registry
- ✅ Feature categorization (team_stats, player_stats, historical, odds)
- ✅ Feature type tracking (numerical, categorical, boolean, text, embedding)
- ✅ Transformation logic documentation
- ✅ Feature versioning
- ✅ Dependency tracking

---

## Enum Types (9 enums)

| Enum Name | Values | Used In |
|-----------|--------|---------|
| `model_status` | development, testing, staging, production, deprecated, archived | `ml_models.model_status` |
| `run_status` | queued, running, completed, failed, cancelled | `ml_training_runs.run_status` |
| `trigger_type` | manual, scheduled, continuous_learning, ab_test | `ml_training_runs.trigger_type` |
| `evaluation_dataset` | training, validation, test, production | `ml_model_performance.evaluation_dataset` |
| `deployment_environment` | development, staging, production | `ml_model_deployments.deployment_environment` |
| `deployment_status` | deploying, active, inactive, failed, rolled_back | `ml_model_deployments.deployment_status` |
| `deployment_strategy` | blue_green, canary, rolling, immediate | `ml_model_deployments.deployment_strategy` |
| `explanation_type` | shap, lime, feature_importance, attention | `ml_prediction_explanations.explanation_type` |
| `feature_type` | numerical, categorical, boolean, text, embedding | `ml_features.feature_type` |
| `importance_method` | gini, permutation, shap, gain | `ml_feature_importance.importance_method` |
| `test_status` | draft, running, completed, cancelled | `ml_ab_tests.test_status` |
| `winner` | champion, challenger, inconclusive | `ml_ab_test_results.winner` |

---

## JSONB Fields (15 fields)

| Table | Field | Purpose |
|-------|-------|---------|
| `ml_models` | `hyperparameters` | Model hyperparameters |
| `ml_training_runs` | `hyperparameters` | Run-specific hyperparameters |
| `ml_training_runs` | `dataset_config` | Dataset configuration |
| `ml_training_runs` | `early_stopping_config` | Early stopping settings |
| `ml_training_runs` | `training_logs` | Complete training logs |
| `ml_training_metrics` | `additional_metrics` | Precision, recall, F1, etc. |
| `ml_model_performance` | `confusion_matrix` | Confusion matrix |
| `ml_model_performance` | `classification_report` | Detailed metrics |
| `ml_model_performance` | `performance_by_market` | Market breakdown |
| `ml_model_performance` | `performance_by_league` | League breakdown |
| `ml_model_performance` | `performance_by_confidence` | Confidence breakdown |
| `ml_model_deployments` | `deployment_config` | Deployment configuration |
| `ml_predictions` | `raw_output` | Raw model output |
| `ml_predictions` | `feature_values` | Input feature values |
| `ml_prediction_explanations` | `explanation_data` | Explanation values |
| `ml_prediction_explanations` | `top_features` | Top contributing features |
| `ml_features` | `transformation_logic` | Feature calculation logic |
| `ml_feature_engineering` | `dependencies` | Feature dependencies |
| `ml_ab_test_results` | `detailed_metrics` | Detailed comparison |

---

## Storage Estimates

### Year 1 Projections

| Table | Rows | Avg Row Size | Total Size |
|-------|------|--------------|------------|
| `ml_models` | 100 | 2 KB | ~200 KB |
| `ml_training_runs` | 1K | 3 KB | ~3 MB |
| `ml_training_metrics` | 100K | 500 bytes | ~50 MB |
| `ml_model_performance` | 10K | 2 KB | ~20 MB |
| `ml_model_deployments` | 500 | 1 KB | ~500 KB |
| `ml_predictions` | 500K | 1.5 KB | ~750 MB |
| `ml_prediction_explanations` | 500K | 1 KB | ~500 MB |
| `ml_features` | 500 | 1 KB | ~500 KB |
| `ml_feature_importance` | 100K | 300 bytes | ~30 MB |
| `ml_feature_engineering` | 2K | 2 KB | ~4 MB |
| `ml_ab_tests` | 100 | 800 bytes | ~80 KB |
| `ml_ab_test_results` | 2K | 600 bytes | ~1.2 MB |
| **Total (ml_models schema)** | | | **~1.4 GB** |

**Note**: Includes indexes (~2x data size), so total storage: **~4.2 GB** for ml_models schema in Year 1.

---

## Cross-Schema Relationships

- `ml_models` → `users.users` (created_by_user_id)
- `ml_training_runs` → `users.users` (triggered_by_user_id)
- `ml_model_deployments` → `users.users` (deployed_by_user_id)
- `ml_predictions` → `predictions.matches` (match_id)
- `ml_predictions` → `users.expert_profiles` (overridden_by_expert_id)
- `ml_feature_engineering` → `users.users` (created_by_user_id)
- `ml_ab_tests` → `users.users` (created_by_user_id)

---

## ML Workflow

### 1. Model Development
1. Create model entry in `ml_models` (status: development)
2. Define features in `ml_features`
3. Create feature engineering logic in `ml_feature_engineering`

### 2. Training
1. Trigger training run → `ml_training_runs` (status: queued → running)
2. Store epoch metrics → `ml_training_metrics`
3. Calculate feature importance → `ml_feature_importance`
4. Complete training → `ml_training_runs` (status: completed)
5. Update model with S3 path → `ml_models.s3_model_path`

### 3. Evaluation
1. Evaluate on test set → `ml_model_performance`
2. Calculate metrics (accuracy, precision, recall, F1, AUC-ROC)
3. Analyze performance by market, league, confidence
4. Check calibration error

### 4. A/B Testing
1. Create A/B test → `ml_ab_tests` (champion vs challenger)
2. Deploy challenger with traffic split
3. Collect results → `ml_ab_test_results`
4. Calculate statistical significance
5. Determine winner

### 5. Deployment
1. Create deployment → `ml_model_deployments` (status: deploying)
2. Deploy to environment (development, staging, production)
3. Monitor latency and RPS
4. Activate deployment → `ml_model_deployments` (status: active)
5. Update model → `ml_models.is_deployed = true`

### 6. Prediction
1. Generate prediction → `ml_predictions`
2. Store raw output and probabilities
3. Calculate confidence score
4. Flag for expert review if low confidence
5. Generate explanation → `ml_prediction_explanations`

### 7. Continuous Learning
1. Collect expert overrides
2. Analyze override patterns
3. Trigger retraining with expert feedback
4. Evaluate new model
5. A/B test against current champion

---

## Performance Considerations

### Query Patterns Optimized For:
- ✅ Champion model lookup (is_champion = true)
- ✅ Deployed models (is_deployed = true)
- ✅ Training run history by model
- ✅ Latest performance metrics
- ✅ Active deployments
- ✅ Predictions flagged for review
- ✅ Feature importance rankings
- ✅ A/B test results

### Potential Bottlenecks:
- ⚠️ `ml_training_metrics` - High row count for long training runs
- ⚠️ `ml_predictions` - High volume (500K+ rows)
- ⚠️ `ml_prediction_explanations` - High volume with large JSONB
- ⚠️ `ml_feature_importance` - High row count

### Optimization Strategies:
- 📊 Partition `ml_training_metrics` by training_run_id
- 📊 Partition `ml_predictions` by created_at (monthly)
- 📊 Archive old training runs and metrics
- 📊 Use read replicas for analytics queries
- 📊 Cache champion model in Redis
- 📊 Compress JSONB fields

---

## Next Steps

1. ✅ **Review ER diagram** - Stakeholder approval
2. 🔄 **Create Alembic migrations** (KAN-16)
3. 🔄 **Implement SQLAlchemy models** (KAN-19)
4. 🔄 **Write unit tests** for constraints
5. 🔄 **ML pipeline integration**
6. 🔄 **Model serving infrastructure**
7. 🔄 **Monitoring and alerting**

---

## Related Documentation

- **Detailed ER Diagram**: [ml-models-schema-er-diagram.md](./ml-models-schema-er-diagram.md)
- **Database Overview**: [README.md](./README.md)
- **Users Schema**: [users-schema-er-diagram.md](./users-schema-er-diagram.md)
- **Predictions Schema**: [predictions-schema-er-diagram.md](./predictions-schema-er-diagram.md)

---

**Status**: ✅ Ready for Implementation  
**Jira Task**: KAN-94 (Complete)  
**Next Task**: KAN-95 (Analytics Schema ER Diagram)

