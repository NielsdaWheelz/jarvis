"""Private originals and immutable ingress references.

Revision ID: 0011
Revises: 0010
"""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating attachments")
    op.execute("""
      CREATE FUNCTION jarvis_attachment_source_key(value jsonb) RETURNS text
      LANGUAGE sql IMMUTABLE STRICT AS $$
        SELECT encode(sha256(convert_to('{' || string_agg(
          to_jsonb(key)::text || ':' || item::text, ',' ORDER BY key COLLATE "C")
          || '}', 'UTF8')), 'hex') FROM jsonb_each(value) AS entry(key,item)
      $$;

      CREATE FUNCTION jarvis_attachment_source_valid(value jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE STRICT AS $$
      DECLARE field text; item jsonb;
      BEGIN
        IF jsonb_typeof(value) <> 'object' THEN RETURN false; END IF;
        IF value->>'kind' = 'discord' THEN
          IF NOT value ?& ARRAY['kind','guild_id','channel_id','message_id',
            'attachment_id'] OR value - ARRAY['kind','guild_id','channel_id',
            'message_id','attachment_id'] <> '{}'::jsonb THEN RETURN false; END IF;
          FOREACH field IN ARRAY ARRAY['guild_id','channel_id','message_id',
            'attachment_id'] LOOP
            IF jsonb_typeof(value->field) <> 'string'
              OR value->>field !~ '^[1-9][0-9]{0,19}$' THEN RETURN false; END IF;
            IF (value->>field)::numeric > 18446744073709551615
              THEN RETURN false; END IF;
          END LOOP;
          RETURN true;
        ELSIF value->>'kind' = 'gmail' THEN
          IF NOT value ?& ARRAY['kind','account','message_id','part_id'] OR
            value - ARRAY['kind','account','message_id','part_id'] <> '{}'::jsonb
            THEN RETURN false; END IF;
          FOREACH field IN ARRAY ARRAY['account','message_id','part_id'] LOOP
            item := value->field;
            IF jsonb_typeof(item) <> 'string' OR
              octet_length(value->>field) > 1024 OR
              (field <> 'part_id' AND octet_length(value->>field) = 0)
              THEN RETURN false; END IF;
          END LOOP;
          RETURN true;
        END IF;
        RETURN false;
      END $$;

      CREATE TABLE attachment (
        id uuid PRIMARY KEY,
        source jsonb NOT NULL CONSTRAINT ck_attachment_source
          CHECK (jarvis_attachment_source_valid(source)),
        source_key text NOT NULL CONSTRAINT ck_attachment_source_key
          CHECK (source_key = jarvis_attachment_source_key(source)),
        r2_account text NOT NULL CONSTRAINT ck_attachment_account
          CHECK (length(r2_account) > 0),
        bucket text NOT NULL CONSTRAINT ck_attachment_bucket
          CHECK (length(bucket) > 0),
        origin_message_id uuid NOT NULL REFERENCES message(id) ON DELETE RESTRICT,
        capture_action_id uuid UNIQUE REFERENCES action(id) ON DELETE RESTRICT,
        filename text,
        media_type text CONSTRAINT ck_attachment_media_type
          CHECK (media_type IS NULL OR octet_length(media_type) <= 255),
        advertised_size bigint CONSTRAINT ck_attachment_advertised_size
          CHECK (advertised_size IS NULL OR advertised_size >= 0),
        size_bytes bigint,
        sha256 text,
        state text NOT NULL CONSTRAINT ck_attachment_state
          CHECK (state IN ('pending','ready','failed','deleting','deleted')),
        put_entered_at timestamptz,
        stored_at timestamptz,
        deleted_at timestamptz,
        delete_action_id uuid REFERENCES action(id) ON DELETE RESTRICT,
        error text CONSTRAINT ck_attachment_error CHECK (error IS NULL OR error IN (
          'NotFound','TooLarge','ProviderResponseTooLarge','SourceChanged',
          'Unavailable','Pending','CaptureUnresolved','StorageConflict','Deleting',
          'DeleteUnresolved','CacheCleanupFailed','Deleted')),
        created_at timestamptz NOT NULL,
        CONSTRAINT ck_attachment_capture CHECK (
          capture_action_id IS NOT NULL OR source->>'kind' = 'discord'),
        CONSTRAINT ck_attachment_bytes CHECK (
          ((size_bytes IS NULL AND sha256 IS NULL) OR
          (size_bytes BETWEEN 0 AND 104857600 AND sha256 ~ '^[0-9a-f]{64}$')) IS TRUE),
        CONSTRAINT ck_attachment_put CHECK (
          put_entered_at IS NULL OR size_bytes IS NOT NULL),
        CONSTRAINT ck_attachment_stored CHECK (
          (state IN ('ready','deleting','deleted')) = (stored_at IS NOT NULL)
          AND (stored_at IS NULL OR put_entered_at IS NOT NULL)),
        CONSTRAINT ck_attachment_deleted CHECK (
          (state = 'deleted') = (deleted_at IS NOT NULL)),
        CONSTRAINT ck_attachment_delete_lineage CHECK (
          (state IN ('deleting','deleted')) = (delete_action_id IS NOT NULL)),
        CONSTRAINT ck_attachment_outcome CHECK (
          (state = 'pending' AND (error IS NULL OR
            error IN ('CaptureUnresolved','StorageConflict'))) OR
          (state IN ('ready','deleted') AND error IS NULL) OR
          (state = 'deleting' AND (error IS NULL OR error IN
            ('StorageConflict','DeleteUnresolved','CacheCleanupFailed',
             'Unavailable'))) OR
          (state = 'failed' AND error IS NOT NULL AND error IN ('NotFound','TooLarge',
            'ProviderResponseTooLarge','SourceChanged','Unavailable')))
      );
      CREATE UNIQUE INDEX uq_attachment_active_source ON attachment(source_key)
        WHERE state IN ('pending','ready','deleting');
      CREATE INDEX ix_attachment_ingress_pending ON attachment(created_at,id)
        WHERE capture_action_id IS NULL AND state = 'pending' AND error IS NULL;
      GRANT SELECT, INSERT ON attachment TO jarvis_runtime;
      GRANT UPDATE (size_bytes,sha256,state,put_entered_at,stored_at,deleted_at,
        delete_action_id,error) ON attachment TO jarvis_runtime;

      CREATE FUNCTION jarvis_guard_attachment() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'attachment attribution is permanent';
        ELSIF TG_OP = 'INSERT' THEN
          IF NEW.state <> 'pending' THEN
            RAISE EXCEPTION 'new attachments must be pending';
          END IF;
          RETURN NEW;
        END IF;
        IF (to_jsonb(NEW) - ARRAY['size_bytes','sha256','state','put_entered_at',
            'stored_at','deleted_at','delete_action_id','error']) IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['size_bytes','sha256','state','put_entered_at',
            'stored_at','deleted_at','delete_action_id','error']) THEN
          RAISE EXCEPTION 'attachment identity and original metadata are immutable';
        END IF;
        IF (OLD.size_bytes IS NOT NULL AND
              (NEW.size_bytes,NEW.sha256) IS DISTINCT FROM
              (OLD.size_bytes,OLD.sha256))
          OR (OLD.put_entered_at IS NOT NULL AND
              NEW.put_entered_at IS DISTINCT FROM OLD.put_entered_at)
          OR (OLD.stored_at IS NOT NULL AND
              NEW.stored_at IS DISTINCT FROM OLD.stored_at)
          OR (OLD.deleted_at IS NOT NULL AND
              NEW.deleted_at IS DISTINCT FROM OLD.deleted_at)
          OR (OLD.delete_action_id IS NOT NULL AND
              NEW.delete_action_id IS DISTINCT FROM OLD.delete_action_id) THEN
          RAISE EXCEPTION 'attachment byte facts and effect lineage are write-once';
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
          (OLD.state = 'pending' AND NEW.state IN ('ready','failed')) OR
          (OLD.state = 'ready' AND NEW.state = 'deleting') OR
          (OLD.state = 'deleting' AND NEW.state = 'deleted')) THEN
          RAISE EXCEPTION 'invalid attachment state transition';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER attachment_facts BEFORE INSERT OR UPDATE OR DELETE
        ON attachment FOR EACH ROW EXECUTE FUNCTION jarvis_guard_attachment();

      CREATE FUNCTION jarvis_attachment_manifest_valid(value jsonb) RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE STRICT AS $$
      DECLARE entry jsonb; seen text[] := '{}'; identifier uuid;
      BEGIN
        IF jsonb_typeof(value) <> 'array' THEN RETURN false; END IF;
        IF jsonb_array_length(value) NOT BETWEEN 1 AND 10 THEN RETURN false; END IF;
        FOR entry IN SELECT * FROM jsonb_array_elements(value) LOOP
          IF jsonb_typeof(entry) <> 'object' OR NOT entry ?& ARRAY[
            'id','name','name_truncated','media_type','advertised_size'] OR
            entry - ARRAY['id','name','name_truncated','media_type',
              'advertised_size'] <> '{}'::jsonb OR
            jsonb_typeof(entry->'id') <> 'string' OR
            jsonb_typeof(entry->'name_truncated') <> 'boolean' THEN
            RETURN false;
          END IF;
          BEGIN identifier := (entry->>'id')::uuid;
          EXCEPTION WHEN invalid_text_representation THEN RETURN false; END;
          IF identifier::text <> entry->>'id' OR identifier::text = ANY(seen)
            THEN RETURN false; END IF;
          seen := array_append(seen, identifier::text);
          IF entry->'name' <> 'null'::jsonb AND
            (jsonb_typeof(entry->'name') <> 'string' OR
              octet_length(entry->>'name') > 240) THEN RETURN false; END IF;
          IF entry->'media_type' <> 'null'::jsonb AND
            (jsonb_typeof(entry->'media_type') <> 'string' OR
              octet_length(entry->>'media_type') > 255) THEN RETURN false; END IF;
          IF entry->'advertised_size' <> 'null'::jsonb THEN
            IF jsonb_typeof(entry->'advertised_size') <> 'number' OR
              entry->>'advertised_size' !~ '^[0-9]+$' THEN RETURN false; END IF;
            IF (entry->>'advertised_size')::numeric > 9223372036854775807
              THEN RETURN false; END IF;
          END IF;
        END LOOP;
        RETURN true;
      END $$;
      ALTER TABLE message DROP CONSTRAINT ck_message_text_nonempty;
      ALTER TABLE message ADD CONSTRAINT ck_message_attachment_manifest CHECK (
        NOT trace ? 'attachment_manifest' OR (role = 'owner' AND
          source = 'discord' AND
          jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE);
      ALTER TABLE message ADD CONSTRAINT ck_message_text_nonempty CHECK (
        length(text) > 0 OR (role = 'owner' AND source = 'discord' AND
          jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE);
      CREATE OR REPLACE FUNCTION jarvis_guard_message_cause() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.parent_request_id IS DISTINCT FROM OLD.parent_request_id
          OR NEW.trace->'action_id' IS DISTINCT FROM OLD.trace->'action_id'
          OR NEW.trace->'observed_at' IS DISTINCT FROM OLD.trace->'observed_at'
          OR NEW.trace->'attachment_manifest' IS DISTINCT FROM
             OLD.trace->'attachment_manifest' THEN
          RAISE EXCEPTION 'message cause and observation identity are immutable';
        END IF;
        RETURN NEW;
      END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("attachment originals require forward repair")
