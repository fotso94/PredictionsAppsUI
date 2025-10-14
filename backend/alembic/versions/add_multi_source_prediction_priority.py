"""Add multi-source prediction priority system

Revision ID: 2a4f8c9d1e3b
Revises: 9b3c8646a52d
Create Date: 2025-10-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2a4f8c9d1e3b'
down_revision = '9b3c8646a52d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add multi-source prediction priority system fields
    
    Changes:
    1. Add priority_level INTEGER field (0-100 range)
    2. Add superseded_by UUID field for prediction supersession tracking
    3. Update PredictionSource enum with new values
    4. Create composite index for efficient priority-based queries
    5. Update existing predictions with priority levels
    """
    
    # 1. Add new enum values to PredictionSource
    # Note: Enum types are in the 'users' schema (from initial migration)
    # Enum values are uppercase
    op.execute("""
        ALTER TYPE users.predictionsource
        ADD VALUE IF NOT EXISTS 'LLM_GENERATED';
    """)
    op.execute("""
        ALTER TYPE users.predictionsource
        ADD VALUE IF NOT EXISTS 'API_FOOTBALL_BASELINE';
    """)
    op.execute("""
        ALTER TYPE users.predictionsource
        ADD VALUE IF NOT EXISTS 'DEFAULT_RANDOMIZED';
    """)
    
    # 2. Add priority_level column
    op.add_column(
        'predictions',
        sa.Column(
            'priority_level',
            sa.Integer(),
            nullable=True,  # Temporarily nullable for migration
            comment='Prediction priority level (0-100): Expert=100, LLM=50, API-Football=25, Randomized=0'
        ),
        schema='predictions'
    )
    
    # 3. Add superseded_by column for tracking prediction supersession
    op.add_column(
        'predictions',
        sa.Column(
            'superseded_by',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='ID of prediction that supersedes this one (for expert overrides)'
        ),
        schema='predictions'
    )
    
    # 4. Add foreign key constraint for superseded_by
    op.create_foreign_key(
        'fk_predictions_superseded_by',
        'predictions', 'predictions',
        ['superseded_by'], ['id'],
        source_schema='predictions',
        referent_schema='predictions',
        ondelete='SET NULL'
    )
    
    # 5. Update existing predictions with priority levels based on source
    # Note: Enum values are uppercase in the database
    op.execute("""
        UPDATE predictions.predictions
        SET priority_level = CASE
            WHEN source IN ('EXPERT_MANUAL', 'EXPERT_OVERRIDE') THEN 100
            WHEN source = 'ML_BASELINE' THEN 40
            WHEN source = 'ADMIN_MANUAL' THEN 90
            ELSE 0
        END
        WHERE priority_level IS NULL;
    """)
    
    # 6. Make priority_level NOT NULL after populating existing data
    op.alter_column(
        'predictions',
        'priority_level',
        nullable=False,
        schema='predictions'
    )
    
    # 7. Add check constraint for priority_level range
    op.create_check_constraint(
        'ck_predictions_priority_level_range',
        'predictions',
        'priority_level >= 0 AND priority_level <= 100',
        schema='predictions'
    )
    
    # 8. Create composite index for efficient priority-based queries
    # This index supports queries like: "Get highest priority prediction for match X"
    op.create_index(
        'idx_predictions_match_priority_published',
        'predictions',
        ['match_id', sa.text('priority_level DESC'), sa.text('published_at DESC')],
        unique=False,
        schema='predictions'
    )
    
    # 9. Create index on superseded_by for reverse lookups
    op.create_index(
        'idx_predictions_superseded_by',
        'predictions',
        ['superseded_by'],
        unique=False,
        schema='predictions'
    )
    
    print("✅ Multi-source prediction priority system migration completed successfully")


def downgrade() -> None:
    """
    Rollback multi-source prediction priority system changes
    """
    
    # 1. Drop indexes
    op.drop_index(
        'idx_predictions_superseded_by',
        table_name='predictions',
        schema='predictions'
    )
    op.drop_index(
        'idx_predictions_match_priority_published',
        table_name='predictions',
        schema='predictions'
    )
    
    # 2. Drop check constraint
    op.drop_constraint(
        'ck_predictions_priority_level_range',
        'predictions',
        schema='predictions',
        type_='check'
    )
    
    # 3. Drop foreign key constraint
    op.drop_constraint(
        'fk_predictions_superseded_by',
        'predictions',
        schema='predictions',
        type_='foreignkey'
    )
    
    # 4. Drop columns
    op.drop_column('predictions', 'superseded_by', schema='predictions')
    op.drop_column('predictions', 'priority_level', schema='predictions')
    
    # Note: Cannot remove enum values in PostgreSQL without recreating the type
    # This is a known limitation. New enum values will remain but won't be used.
    print("⚠️  Note: New PredictionSource enum values (llm_generated, api_football_baseline, default_randomized) cannot be removed without recreating the enum type.")
    print("✅ Multi-source prediction priority system rollback completed")

