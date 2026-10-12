ALTER TABLE "cashout_accounts" DROP CONSTRAINT "cashout_accounts_member_id_fkey"
ALTER TABLE "cashouts" DROP CONSTRAINT "cashouts_member_id_fkey"
ALTER TABLE "cashouts" DROP CONSTRAINT "cashouts_account_id_fkey"
ALTER TABLE "cashouts" DROP CONSTRAINT "cashouts_debit_entry_id_fkey"
ALTER TABLE "ledger_entries" DROP CONSTRAINT "ledger_entries_member_id_fkey"
DROP INDEX "public"."cashouts_one_pending_per_member"
ALTER TABLE "cashouts" DROP CONSTRAINT "cashouts_amount_cents_check"
ALTER TABLE "cashout_accounts" DROP COLUMN "member_id"
ALTER TABLE "cashout_accounts" ADD "member_id" integer NOT NULL
ALTER TABLE "cashout_accounts" ADD CONSTRAINT "FK_706f9050252ea8c813667fc4171" FOREIGN KEY ("member_id") REFERENCES "members"("id") ON DELETE NO ACTION ON UPDATE NO ACTION
ALTER TABLE "ledger_entries" ADD CONSTRAINT "FK_41397e666eebc23fa6f148268fc" FOREIGN KEY ("member_id") REFERENCES "members"("id") ON DELETE NO ACTION ON UPDATE NO ACTION
