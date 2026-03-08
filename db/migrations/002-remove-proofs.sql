ALTER TABLE historical_data DROP COLUMN IF EXISTS proof_tx_hash;
ALTER TABLE historical_data DROP COLUMN IF EXISTS output_hash;
ALTER TABLE historical_data DROP COLUMN IF EXISTS gas_paid_wei;
ALTER TABLE historical_data DROP COLUMN IF EXISTS gas_paid_usd;
ALTER TABLE historical_data DROP COLUMN IF EXISTS builder_reward_usd;
ALTER TABLE active_jobs DROP COLUMN IF EXISTS client_builder_code;
UPDATE historical_data SET status = 'completed' WHERE status = 'completed_no_proof';
