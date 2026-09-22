"""add notification taxonomy fields (notif_type, priority, title, trip/vehicle links, dedup)

Revision ID: f1a2b3c4d5e6
Revises: 9c0c08364078
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = '9c0c08364078'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trip_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('vehicle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('notif_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('title', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('priority', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('action_type', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('dedup_key', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('active', sa.Boolean(), nullable=True))
        batch_op.create_index(batch_op.f('ix_notifications_trip_id'), ['trip_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_vehicle_id'), ['vehicle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_notif_type'), ['notif_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_priority'), ['priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_dedup_key'), ['dedup_key'], unique=False)
        batch_op.create_foreign_key('fk_notifications_trip_id', 'trips', ['trip_id'], ['id'])
        batch_op.create_foreign_key('fk_notifications_vehicle_id', 'vehicles', ['vehicle_id'], ['id'])

    # Backfill existing rows: derive notif_type from the legacy `category`
    # string, and priority from the legacy `severity` string, so nothing
    # already in the table ends up with NULLs the app doesn't expect.
    conn = op.get_bind()
    category_map = {
        'weather': 'WEATHER',
        'traffic': 'TRIP',
        'fuel': 'VEHICLE',
        'maintenance': 'VEHICLE',
        'route_deviation': 'TRIP',
        'reroute': 'TRIP',
        'sos': 'SYSTEM',
        'anomaly': 'CARBON',
        'carbon_budget': 'CARBON',
        'document_expiry': 'VEHICLE',
        'daily_report': 'SYSTEM',
        'approval': 'SYSTEM',
        'registration': 'SYSTEM',
    }
    severity_map = {'info': 'INFO', 'success': 'INFO', 'warning': 'WARNING', 'critical': 'CRITICAL'}

    notifications = sa.table(
        'notifications',
        sa.column('id', sa.Integer),
        sa.column('category', sa.String),
        sa.column('severity', sa.String),
        sa.column('notif_type', sa.String),
        sa.column('priority', sa.String),
        sa.column('active', sa.Boolean),
    )
    rows = conn.execute(sa.select(notifications.c.id, notifications.c.category, notifications.c.severity)).fetchall()
    for row in rows:
        notif_type = category_map.get((row.category or '').lower(), 'SYSTEM')
        priority = severity_map.get((row.severity or '').lower(), 'INFO')
        conn.execute(
            notifications.update()
            .where(notifications.c.id == row.id)
            .values(notif_type=notif_type, priority=priority, active=False)
        )

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.alter_column('notif_type', existing_type=sa.String(length=20), nullable=False, server_default='SYSTEM')
        batch_op.alter_column('priority', existing_type=sa.String(length=20), nullable=False, server_default='INFO')
        batch_op.alter_column('active', existing_type=sa.Boolean(), nullable=False, server_default=sa.false())
        batch_op.create_check_constraint(
            'ck_notif_type_valid', "notif_type IN ('TRIP','WEATHER','VEHICLE','CARBON','SYSTEM')"
        )
        batch_op.create_check_constraint(
            'ck_notif_priority_valid', "priority IN ('INFO','ACTION','WARNING','CRITICAL')"
        )


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notif_priority_valid', type_='check')
        batch_op.drop_constraint('ck_notif_type_valid', type_='check')
        batch_op.drop_constraint('fk_notifications_vehicle_id', type_='foreignkey')
        batch_op.drop_constraint('fk_notifications_trip_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_notifications_dedup_key'))
        batch_op.drop_index(batch_op.f('ix_notifications_priority'))
        batch_op.drop_index(batch_op.f('ix_notifications_notif_type'))
        batch_op.drop_index(batch_op.f('ix_notifications_vehicle_id'))
        batch_op.drop_index(batch_op.f('ix_notifications_trip_id'))
        batch_op.drop_column('active')
        batch_op.drop_column('dedup_key')
        batch_op.drop_column('action_type')
        batch_op.drop_column('priority')
        batch_op.drop_column('title')
        batch_op.drop_column('notif_type')
        batch_op.drop_column('vehicle_id')
        batch_op.drop_column('trip_id')
