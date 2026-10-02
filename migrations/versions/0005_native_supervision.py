"""Native attempts, callbacks and canonical request control.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE message
      ADD COLUMN request_state text,
      ADD COLUMN wait_reason text,
      ADD COLUMN control_kind text,
      ADD COLUMN control_sequence integer UNIQUE,
      ADD COLUMN control_targets uuid[];
    UPDATE message SET request_state = CASE WHEN processed_at IS NULL THEN 'pending'
    ELSE 'completed' END
      WHERE role = 'owner';
    ALTER TABLE message ADD CONSTRAINT ck_message_request_state
      CHECK (request_state IS NULL OR request_state IN
    ('pending','waiting','completed','stopped'));
    ALTER TABLE message ADD CONSTRAINT ck_message_wait_reason_required
      CHECK ((request_state IS NOT DISTINCT FROM 'waiting') = (wait_reason IS NOT
    NULL));
    ALTER TABLE message ADD CONSTRAINT ck_message_wait_reason
      CHECK (wait_reason IS NULL OR wait_reason IN
    ('approval','external_reconciliation','owner_input','configuration'));
    ALTER TABLE message ADD CONSTRAINT ck_message_control
      CHECK ((control_kind IS NULL AND control_sequence IS NULL AND control_targets IS
    NULL)
        OR (control_kind IN ('stop','pause','resume') AND control_sequence > 0 AND
    control_targets IS NOT NULL));
    CREATE SEQUENCE message_control_sequence;
    CREATE INDEX ix_message_unresolved_request ON
    message(source_conversation_id,created_at,id)
      WHERE request_state IN ('pending','waiting');
    ALTER TABLE action ADD COLUMN supersedes_action_id uuid UNIQUE REFERENCES action(id)
    ON DELETE RESTRICT;
    ALTER TABLE model_decision ADD COLUMN submission jsonb;
    ALTER TABLE model_decision ADD CONSTRAINT ck_model_decision_exclusive_outcome
      CHECK (terminal IS NULL OR submission IS NULL);
    ALTER TABLE model_decision ADD CONSTRAINT ck_model_decision_submission_object
      CHECK (submission IS NULL OR jsonb_typeof(submission) = 'object');
    """)
    op.execute("""
CREATE TABLE native_attempt (
    id UUID NOT NULL,
    conversation_id TEXT NOT NULL,
    attempt_seq INTEGER NOT NULL,
    owner_epoch TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    request JSONB NOT NULL,
    native_binding JSONB,
    submission_evidence JSONB,
    local_outcome JSONB,
    terminal JSONB,
    product_outcome JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    armed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    fenced_at TIMESTAMP WITH TIME ZONE,
    terminal_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_native_attempt PRIMARY KEY (id),
    CONSTRAINT uq_native_attempt_conversation_id UNIQUE (conversation_id, attempt_seq),
    CONSTRAINT ck_native_attempt_sequence_positive CHECK (attempt_seq > 0),
    CONSTRAINT ck_native_attempt_fingerprint CHECK (request_fingerprint ~
    '^[0-9a-f]{64}$'),
    CONSTRAINT ck_native_attempt_request_object CHECK (jsonb_typeof(request) =
    'object'),
    CONSTRAINT ck_native_attempt_terminal_time CHECK ((terminal IS NULL) = (terminal_at
    IS NULL)),
    CONSTRAINT ck_native_attempt_product_terminal CHECK (product_outcome IS NULL OR
    terminal IS NOT NULL),
    CONSTRAINT ck_native_attempt_native_binding_object CHECK (native_binding IS NULL OR
    jsonb_typeof(native_binding) = 'object'),
    CONSTRAINT ck_native_attempt_submission_evidence_object CHECK (submission_evidence
    IS NULL OR jsonb_typeof(submission_evidence) = 'object'),
    CONSTRAINT ck_native_attempt_local_outcome_object CHECK (local_outcome IS NULL OR
    jsonb_typeof(local_outcome) = 'object'),
    CONSTRAINT ck_native_attempt_terminal_object CHECK (terminal IS NULL OR
    jsonb_typeof(terminal) = 'object'),
    CONSTRAINT ck_native_attempt_product_outcome_object CHECK (product_outcome IS NULL
    OR jsonb_typeof(product_outcome) = 'object')
)
    """)
    op.execute("""
CREATE UNIQUE INDEX uq_native_attempt_active ON native_attempt (conversation_id) WHERE
    fenced_at IS NULL AND product_outcome IS NULL
    """)
    op.execute("""
CREATE TABLE native_invocation (
    id UUID NOT NULL,
    attempt_id UUID NOT NULL,
    ordinal INTEGER NOT NULL,
    native_call_id TEXT NOT NULL,
    request_message_id UUID,
    tool_id TEXT NOT NULL,
    proposal_digest TEXT NOT NULL,
    proposal JSONB NOT NULL,
    frozen_contract JSONB NOT NULL,
    validation TEXT NOT NULL,
    validation_error JSONB,
    read_position TEXT,
    action_id UUID,
    reply_receipt JSONB,
    reply_recorded_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_native_invocation PRIMARY KEY (id),
    CONSTRAINT uq_native_invocation_call UNIQUE (attempt_id, native_call_id),
    CONSTRAINT uq_native_invocation_ordinal UNIQUE (attempt_id, ordinal),
    CONSTRAINT ck_native_invocation_ordinal_positive CHECK (ordinal > 0),
    CONSTRAINT ck_native_invocation_digest CHECK (proposal_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_native_invocation_proposal_object CHECK (jsonb_typeof(proposal) =
    'object'),
    CONSTRAINT ck_native_invocation_contract_object CHECK (jsonb_typeof(frozen_contract)
    = 'object'),
    CONSTRAINT ck_native_invocation_validation CHECK (validation IN ('accepted',
    'rejected')),
    CONSTRAINT ck_native_invocation_validation_error CHECK ((validation = 'rejected') =
    (validation_error IS NOT NULL)),
    CONSTRAINT ck_native_invocation_one_execution CHECK (read_position IS NULL OR
    action_id IS NULL),
    CONSTRAINT ck_native_invocation_write_origin CHECK ((validation = 'accepted' AND
    frozen_contract->>'effect' = 'Write') IS NOT DISTINCT FROM (request_message_id IS
    NOT NULL)),
    CONSTRAINT ck_native_invocation_rejected_execution CHECK (validation <> 'rejected'
    OR (read_position IS NULL AND action_id IS NULL AND request_message_id IS NULL)),
    CONSTRAINT ck_native_invocation_reply_time CHECK ((reply_receipt IS NULL) =
    (reply_recorded_at IS NULL)),
    CONSTRAINT fk_native_invocation_attempt_id_native_attempt FOREIGN KEY(attempt_id)
    REFERENCES native_attempt (id) ON DELETE RESTRICT,
    CONSTRAINT fk_native_invocation_request_message_id_message FOREIGN
    KEY(request_message_id) REFERENCES message (id) ON DELETE RESTRICT,
    CONSTRAINT fk_native_invocation_read_position_read_position FOREIGN
    KEY(read_position) REFERENCES read_position (position) ON DELETE RESTRICT,
    CONSTRAINT fk_native_invocation_action_id_action FOREIGN KEY(action_id) REFERENCES
    action (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE TABLE native_input_delivery (
    attempt_id UUID NOT NULL,
    message_id UUID NOT NULL,
    ordinal INTEGER NOT NULL,
    delivery_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    provider_evidence JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_native_input_delivery PRIMARY KEY (attempt_id, message_id),
    CONSTRAINT uq_native_input_delivery_attempt_id UNIQUE (attempt_id, ordinal),
    CONSTRAINT ck_native_input_delivery_ordinal_positive CHECK (ordinal > 0),
    CONSTRAINT ck_native_input_delivery_mode CHECK (mode IN ('initial', 'steer')),
    CONSTRAINT ck_native_input_delivery_state CHECK (state IN ('prepared', 'sent',
    'queued', 'recorded', 'rejected')),
    CONSTRAINT fk_native_input_delivery_attempt_id_native_attempt FOREIGN
    KEY(attempt_id) REFERENCES native_attempt (id) ON DELETE RESTRICT,
    CONSTRAINT fk_native_input_delivery_message_id_message FOREIGN KEY(message_id)
    REFERENCES message (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
    GRANT SELECT, INSERT ON native_attempt, native_invocation, native_input_delivery TO
    jarvis_runtime;
    GRANT
    UPDATE(native_binding,submission_evidence,local_outcome,terminal,product_outcome,fenced_at,terminal_at)
      ON native_attempt TO jarvis_runtime;
    GRANT UPDATE(read_position,action_id,reply_receipt,reply_recorded_at) ON
    native_invocation TO jarvis_runtime;
    GRANT UPDATE(state,provider_evidence,updated_at) ON native_input_delivery TO
    jarvis_runtime;
    GRANT
    UPDATE(request_state,wait_reason,control_kind,control_sequence,control_targets) ON
    message TO jarvis_runtime;
    GRANT UPDATE(submission) ON model_decision TO jarvis_runtime;
    GRANT USAGE, SELECT ON SEQUENCE message_control_sequence TO jarvis_runtime;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE native_input_delivery;
    DROP TABLE native_invocation;
    DROP TABLE native_attempt;
    ALTER TABLE action DROP COLUMN supersedes_action_id;
    ALTER TABLE model_decision DROP COLUMN submission;
    DROP INDEX ix_message_unresolved_request;
    ALTER TABLE message DROP COLUMN control_targets, DROP COLUMN control_sequence,
      DROP COLUMN control_kind, DROP COLUMN wait_reason, DROP COLUMN request_state;
    DROP SEQUENCE message_control_sequence;
    """)
