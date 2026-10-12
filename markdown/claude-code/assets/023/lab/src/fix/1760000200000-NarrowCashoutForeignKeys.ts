import { MigrationInterface, QueryRunner } from "typeorm";

// Forward-only: these columns only ever hold values from integer keys.
export class NarrowCashoutForeignKeys1760000200000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`ALTER TABLE cashout_accounts ALTER COLUMN member_id TYPE integer`);
    await queryRunner.query(`ALTER TABLE cashouts ALTER COLUMN member_id TYPE integer`);
    await queryRunner.query(`ALTER TABLE cashouts ALTER COLUMN debit_entry_id TYPE integer`);
  }

  async down(): Promise<void> {
    throw new Error("forward-only");
  }
}
