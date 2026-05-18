-- Predictions table for cascade prediction engine
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    predicted_failure TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    time_to_failure_minutes INT,
    causal_chain JSONB DEFAULT '[]',
    suggested_action TEXT,
    outcome TEXT CHECK (outcome IN ('correct', 'incorrect', 'unresolved')),
    actual_time_to_failure_minutes INT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_predictions_incident_id ON predictions(incident_id);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON predictions(created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_outcome ON predictions(outcome);

-- RLS
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for service role" ON predictions
    FOR ALL USING (true);

-- View for prediction accuracy stats
CREATE OR REPLACE VIEW prediction_accuracy AS
SELECT
    incident_id,
    COUNT(*) as total_predictions,
    COUNT(CASE WHEN outcome = 'correct' THEN 1 END) as correct_predictions,
    COUNT(CASE WHEN outcome = 'incorrect' THEN 1 END) as incorrect_predictions,
    COUNT(CASE WHEN outcome = 'unresolved' THEN 1 END) as unresolved_predictions,
    AVG(CASE
        WHEN outcome = 'correct' AND actual_time_to_failure_minutes IS NOT NULL
        THEN ABS(time_to_failure_minutes - actual_time_to_failure_minutes)
    END) as avg_time_accuracy_minutes
FROM predictions
GROUP BY incident_id;
