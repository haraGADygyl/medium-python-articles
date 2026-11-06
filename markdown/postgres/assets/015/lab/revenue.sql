-- The dashboard query: weekly charging revenue for Nissan Leaf sessions in Atlanta.
SELECT date_trunc('week', s.started_at) AS week,
       round(sum(s.kwh * t.usd_per_kwh), 2) AS revenue_usd
FROM charge_session s
JOIN tariff_rate t
  ON t.state = s.state
 AND t.connector = s.connector
 AND s.started_at <@ t.valid_during
WHERE s.city = 'Atlanta' AND s.state = 'GA'
  AND s.vehicle_make = 'Nissan' AND s.vehicle_model = 'Leaf'
  AND s.connector = 'CHAdeMO'
GROUP BY 1
ORDER BY 1;
