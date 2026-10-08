-- Architect proposal: narrow the projection and bound the result
SELECT id, total, created_at FROM orders WHERE user_id = 123 AND status = 'pending' ORDER BY created_at DESC LIMIT 50
