import { MigrationInterface, QueryRunner } from "typeorm";

// Written by following docs/schema.md: "every id is BIGINT".
export class CreateCashouts1760000100000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE cashout_accounts (
        id BIGSERIAL PRIMARY KEY,
        member_id BIGINT NOT NULL REFERENCES members (id),
        iban_last4 TEXT NOT NULL
      )`);
    await queryRunner.query(`
      CREATE TABLE cashouts (
        id BIGSERIAL PRIMARY KEY,
        member_id BIGINT NOT NULL REFERENCES members (id),
        account_id BIGINT NOT NULL REFERENCES cashout_accounts (id),
        debit_entry_id BIGINT REFERENCES ledger_entries (id),
        amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
        status TEXT NOT NULL DEFAULT 'pending'
      )`);
    await queryRunner.query(`
      CREATE UNIQUE INDEX cashouts_one_pending_per_member
        ON cashouts (member_id) WHERE status = 'pending'`);
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE cashouts`);
    await queryRunner.query(`DROP TABLE cashout_accounts`);
  }
}
