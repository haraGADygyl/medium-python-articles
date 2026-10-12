INSERT INTO members (email) VALUES
  ('a@lab.test'), ('b@lab.test'), ('c@lab.test'), ('d@lab.test'), ('e@lab.test');
INSERT INTO ledger_entries (member_id, delta_cents) VALUES (5, -2500), (3, -900);
INSERT INTO cashout_accounts (id, member_id, iban_last4) VALUES (41, 5, '0042'), (77, 3, '1180');
INSERT INTO cashouts (id, member_id, account_id, debit_entry_id, amount_cents, status) VALUES
  (9001, 5, 41, 1, 2500, 'paid'),
  (9002, 3, 77, 2, 900, 'pending');
