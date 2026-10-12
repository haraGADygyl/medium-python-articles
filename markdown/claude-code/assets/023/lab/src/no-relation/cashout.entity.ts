import { Column, Entity, PrimaryGeneratedColumn } from "typeorm";

@Entity("cashouts")
export class Cashout {
  @PrimaryGeneratedColumn({ type: "bigint" })
  id: number;

  @Column({ type: "bigint", name: "member_id" })
  memberId: number;

  @Column({ type: "bigint", name: "account_id" })
  accountId: number;

  @Column({ type: "bigint", name: "debit_entry_id", nullable: true })
  debitEntryId: number | null;

  @Column({ name: "amount_cents" })
  amountCents: number;

  @Column({ type: "text", default: "pending" })
  status: string;
}
