import { MigrationInterface, QueryRunner } from "typeorm";

// Written months earlier, before the schema doc existed: plain integer keys.
export class CreateCore1760000000000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE members (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE
      )`);
    await queryRunner.query(`
      CREATE TABLE ledger_entries (
        id SERIAL PRIMARY KEY,
        member_id INTEGER NOT NULL REFERENCES members (id),
        delta_cents INTEGER NOT NULL
      )`);
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE ledger_entries`);
    await queryRunner.query(`DROP TABLE members`);
  }
}
