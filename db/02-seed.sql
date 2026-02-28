-- Pre-seeded sample data
-- Inserts realistic historical jobs, costs, snapshots, and attribution logs

INSERT INTO historical_data (id, slurm_job_id, payload, status, x402_tx_hash, price_usdc, gas_paid_usd, output_hash, proof_tx_hash, builder_reward_usd, compute_duration_s, llm_cost_usd, submitted_at, completed_at)
VALUES
  (gen_random_uuid(), 1001, '{"script":"echo hello","nodes":1,"time_limit_min":1}', 'completed', '0xaaa1', 0.0250, 0.0012, decode('abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789','hex'), '0xbbb1', 0, 12.5, 0.0008, now() - interval '23 hours', now() - interval '22.5 hours'),
  (gen_random_uuid(), 1002, '{"script":"python3 sim.py","nodes":2,"time_limit_min":5}', 'completed', '0xaaa2', 0.0450, 0.0015, decode('1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef','hex'), '0xbbb2', 0, 45.2, 0.0008, now() - interval '20 hours', now() - interval '19 hours'),
  (gen_random_uuid(), 1003, '{"script":"./run_bench.sh","nodes":1,"time_limit_min":2}', 'completed', '0xaaa3', 0.0300, 0.0011, decode('fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210','hex'), '0xbbb3', 0, 28.1, 0.0008, now() - interval '15 hours', now() - interval '14.5 hours'),
  (gen_random_uuid(), 1004, '{"script":"mpirun -np 4 solver","nodes":4,"time_limit_min":10}', 'completed', '0xaaa4', 0.1200, 0.0018, decode('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef','hex'), '0xbbb4', 0, 120.7, 0.0008, now() - interval '10 hours', now() - interval '8 hours'),
  (gen_random_uuid(), 1005, '{"script":"echo test","nodes":1,"time_limit_min":1}', 'completed', '0xaaa5', 0.0250, 0.0010, decode('aabbccddee112233aabbccddee112233aabbccddee112233aabbccddee112233','hex'), '0xbbb5', 0, 8.3, 0.0008, now() - interval '5 hours', now() - interval '4.8 hours'),
  (gen_random_uuid(), 1006, '{"script":"python3 train.py","nodes":2,"time_limit_min":3}', 'completed', '0xaaa6', 0.0380, 0.0013, decode('9988776655443322118877665544332211887766554433221188776655443322','hex'), '0xbbb6', 0, 55.9, 0.0008, now() - interval '3 hours', now() - interval '2.5 hours'),
  (gen_random_uuid(), 1007, '{"script":"bash job.sh","nodes":1,"time_limit_min":1}', 'completed', '0xaaa7', 0.0250, 0.0009, decode('1122334455667788112233445566778811223344556677881122334455667788','hex'), '0xbbb7', 0, 15.2, 0.0008, now() - interval '1 hour', now() - interval '50 minutes');

INSERT INTO agent_costs (cost_type, amount_usd, detail, created_at)
VALUES
  ('gas', 0.0012, '{"tx_hash":"0xbbb1"}', now() - interval '22.5 hours'),
  ('llm_inference', 0.0008, '{"model":"openai:gpt-4o-mini","input_tokens":450,"output_tokens":120}', now() - interval '22 hours'),
  ('gas', 0.0015, '{"tx_hash":"0xbbb2"}', now() - interval '19 hours'),
  ('llm_inference', 0.0008, '{"model":"openai:gpt-4o-mini","input_tokens":520,"output_tokens":150}', now() - interval '19 hours'),
  ('gas', 0.0011, '{"tx_hash":"0xbbb3"}', now() - interval '14.5 hours'),
  ('gas', 0.0018, '{"tx_hash":"0xbbb4"}', now() - interval '8 hours'),
  ('llm_inference', 0.0008, '{"model":"openai:gpt-4o-mini","input_tokens":480,"output_tokens":130}', now() - interval '8 hours'),
  ('gas', 0.0010, '{"tx_hash":"0xbbb5"}', now() - interval '4.8 hours'),
  ('gas', 0.0013, '{"tx_hash":"0xbbb6"}', now() - interval '2.5 hours'),
  ('gas', 0.0009, '{"tx_hash":"0xbbb7"}', now() - interval '50 minutes');

INSERT INTO wallet_snapshots (eth_balance, usdc_balance, eth_price_usd, recorded_at)
VALUES
  (42000000000000000, 125.50, 3200.00, now() - interval '24 hours'),
  (41800000000000000, 125.53, 3195.00, now() - interval '23 hours'),
  (41600000000000000, 125.80, 3210.00, now() - interval '20 hours'),
  (41500000000000000, 125.83, 3205.00, now() - interval '15 hours'),
  (41300000000000000, 126.20, 3220.00, now() - interval '10 hours'),
  (41200000000000000, 126.23, 3215.00, now() - interval '5 hours'),
  (41100000000000000, 126.50, 3225.00, now() - interval '1 hour');

INSERT INTO attribution_log (tx_hash, codes, gas_used, created_at)
VALUES
  ('0xbbb1', ARRAY['ouro'], 65000, now() - interval '22.5 hours'),
  ('0xbbb2', ARRAY['ouro','demo-client'], 72000, now() - interval '19 hours'),
  ('0xbbb3', ARRAY['ouro'], 63000, now() - interval '14.5 hours'),
  ('0xbbb4', ARRAY['ouro','demo-client'], 85000, now() - interval '8 hours'),
  ('0xbbb5', ARRAY['ouro'], 61000, now() - interval '4.8 hours'),
  ('0xbbb6', ARRAY['ouro','demo-client'], 68000, now() - interval '2.5 hours'),
  ('0xbbb7', ARRAY['ouro'], 60000, now() - interval '50 minutes');
