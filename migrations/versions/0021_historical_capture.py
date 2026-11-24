"""Retain the retired original addresses after the stopped corpus rewrite."""

from alembic import op
from sqlalchemy import text

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().config.attributes.get("historical_rewrite") is not True:
        raise RuntimeError("use the stopped, snapshot-bound historical capture cut")
    op.execute("""
        CREATE TABLE memory_retired_source_record(
            id uuid PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES source_conversation(id),
            native_event_id text NOT NULL,
            part integer NOT NULL CHECK (part >= 0),
            UNIQUE(conversation_id,native_event_id,part)
        );
        INSERT INTO memory_retired_source_record
            (id,conversation_id,native_event_id,part)
        SELECT id,conversation_id,native_event_id,part FROM pg_temp.cut_retired;
        GRANT SELECT ON memory_retired_source_record TO jarvis_runtime,jarvis_memory;
        CREATE FUNCTION public.memory_reject_retired_source() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS(SELECT FROM public.memory_retired_source_record t
                      WHERE t.id=NEW.id OR (t.conversation_id,t.native_event_id)
                      =(NEW.conversation_id,NEW.native_event_id)) THEN
                RAISE EXCEPTION 'retired source identity'
                    USING ERRCODE='23505', CONSTRAINT='retired_source_identity';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER source_record_reject_retired
            BEFORE INSERT ON public.source_record
            FOR EACH ROW EXECUTE FUNCTION public.memory_reject_retired_source();
    """)
    if op.get_bind().scalar(text("SELECT to_regrole('jarvis_backup') IS NOT NULL")):
        op.execute("GRANT SELECT ON memory_retired_source_record TO jarvis_backup")


def downgrade() -> None:
    raise RuntimeError("historical capture requires forward repair")
