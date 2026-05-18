-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Incidents table
CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Events table with vector embedding
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL CHECK (source IN ('slack', 'screen')),
    actor TEXT NOT NULL DEFAULT 'unknown',
    type TEXT NOT NULL CHECK (type IN ('action', 'hypothesis', 'observation', 'outcome')),
    content TEXT NOT NULL,
    embedding vector(1536),
    raw_ref TEXT,
    confidence REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    references_prior_event UUID REFERENCES events(id)
);

-- Post-mortems table
CREATE TABLE IF NOT EXISTS post_mortems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    timeline JSONB DEFAULT '[]',
    root_cause_hypothesis TEXT,
    actions_and_outcomes JSONB DEFAULT '[]',
    contributing_factors JSONB DEFAULT '[]',
    follow_up_items JSONB DEFAULT '[]',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_events_incident_id ON events(incident_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_post_mortems_incident_id ON post_mortems(incident_id);

-- HNSW index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_events_embedding ON events
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Function for semantic search of similar events
CREATE OR REPLACE FUNCTION search_similar_events(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.85,
    match_count int DEFAULT 5,
    filter_type text DEFAULT NULL
)
RETURNS TABLE (
    event_id uuid,
    incident_id uuid,
    content text,
    type text,
    actor text,
    "timestamp" timestamptz,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id as event_id,
        e.incident_id,
        e.content,
        e.type,
        e.actor,
        e."timestamp",
        1 - (e.embedding <=> query_embedding) as similarity
    FROM events e
    WHERE
        (filter_type IS NULL OR e.type = filter_type)
        AND 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to get incident timeline
CREATE OR REPLACE FUNCTION get_incident_timeline(p_incident_id UUID)
RETURNS TABLE (
    event_id uuid,
    "timestamp" timestamptz,
    source text,
    actor text,
    type text,
    content text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id as event_id,
        e."timestamp",
        e.source,
        e.actor,
        e.type,
        e.content
    FROM events e
    WHERE e.incident_id = p_incident_id
    ORDER BY e."timestamp" ASC;
END;
$$;

-- Row Level Security (RLS) policies
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_mortems ENABLE ROW LEVEL SECURITY;

-- Allow all operations for service role (API key)
CREATE POLICY "Allow all for service role" ON incidents
    FOR ALL USING (true);

CREATE POLICY "Allow all for service role" ON events
    FOR ALL USING (true);

CREATE POLICY "Allow all for service role" ON post_mortems
    FOR ALL USING (true);

-- Views for common queries
CREATE OR REPLACE VIEW active_incidents AS
SELECT * FROM incidents
WHERE status = 'active'
ORDER BY started_at DESC;

CREATE OR REPLACE VIEW incident_event_count AS
SELECT
    i.id as incident_id,
    i.title,
    COUNT(e.id) as event_count,
    COUNT(CASE WHEN e.type = 'action' THEN 1 END) as action_count,
    COUNT(CASE WHEN e.type = 'outcome' THEN 1 END) as outcome_count
FROM incidents i
LEFT JOIN events e ON i.id = e.incident_id
GROUP BY i.id, i.title;
