\set wallet random(1, 1000000)
\set merchant random(1000001, 1010000)
\set amount random(100, 5000)
BEGIN;
UPDATE account SET balance = balance - :amount WHERE id = :wallet AND balance >= :amount;
UPDATE account SET balance = balance + :amount - :amount / 50 WHERE id = :merchant;
INSERT INTO entry (account_id, amount)
VALUES (:wallet, -:amount), (:merchant, :amount - :amount / 50), (0, :amount / 50);
COMMIT;
