-- Add warning_count to incidents table
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS warning_count integer DEFAULT 0;

-- Update events type check to include 'intervention'
ALTER TABLE events DROP CONSTRAINT IF EXISTS events_type_check;
ALTER TABLE events ADD CONSTRAINT events_type_check
    CHECK (type IN ('action', 'hypothesis', 'observation', 'outcome', 'intervention'));

-- Index for faster warning count lookups
CREATE INDEX IF NOT EXISTS idx_incidents_warning_count ON incidents(warning_count);

-- Update events source check to include 'agent'
ALTER TABLE events DROP CONSTRAINT IF EXISTS events_source_check;
ALTER TABLE events ADD CONSTRAINT events_source_check
    CHECK (source IN ('slack', 'screen', 'agent'));

-- Function to atomically increment warning_count and return new value
CREATE OR REPLACE FUNCTION increment_warning_count(p_incident_id UUID)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_count integer;
BEGIN
    UPDATE incidents
    SET warning_count = warning_count + 1
    WHERE id = p_incident_id
    RETURNING warning_count INTO new_count;

    RETURN COALESCE(new_count, 0);
END;
$$;
