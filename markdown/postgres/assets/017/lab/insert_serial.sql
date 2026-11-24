\set ep random(1, 5000)
\set bytes random(200, 10000)
INSERT INTO delivery_serial (endpoint_id, status_code, payload_bytes) VALUES (:ep, 200, :bytes);
