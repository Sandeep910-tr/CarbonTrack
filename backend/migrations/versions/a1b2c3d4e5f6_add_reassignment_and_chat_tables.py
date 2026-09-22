"""add reassignment requests + driver-admin chat tables

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reassignment_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('requesting_driver_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=40), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('request_lat', sa.Float(), nullable=True),
        sa.Column('request_lng', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('replacement_driver_id', sa.Integer(), nullable=True),
        sa.Column('resolved_by_admin_id', sa.Integer(), nullable=True),
        sa.Column('resolution_note', sa.String(length=255), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('Pending','Approved','Rejected')", name='ck_reassignment_status_valid'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id']),
        sa.ForeignKeyConstraint(['requesting_driver_id'], ['drivers.id']),
        sa.ForeignKeyConstraint(['replacement_driver_id'], ['drivers.id']),
        sa.ForeignKeyConstraint(['resolved_by_admin_id'], ['admins.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reassignment_requests_trip_id', 'reassignment_requests', ['trip_id'])
    op.create_index('ix_reassignment_requests_requesting_driver_id', 'reassignment_requests', ['requesting_driver_id'])
    op.create_index('ix_reassignment_requests_status', 'reassignment_requests', ['status'])
    op.create_index('ix_reassignment_requests_requested_at', 'reassignment_requests', ['requested_at'])

    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=True),
        sa.Column('driver_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id']),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversations_trip_id', 'conversations', ['trip_id'])
    op.create_index('ix_conversations_driver_id', 'conversations', ['driver_id'])
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'])

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('sender_role', sa.String(length=10), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("sender_role IN ('driver','admin')", name='ck_message_sender_role_valid'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_is_read', 'messages', ['is_read'])
    op.create_index('ix_messages_created_at', 'messages', ['created_at'])


def downgrade():
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('reassignment_requests')
