import { Column, Entity, JoinColumn, ManyToOne, PrimaryGeneratedColumn } from "typeorm";
import { CashoutAccount } from "./cashout-account.entity";
import { LedgerEntry } from "./ledger-entry.entity";
import { Member } from "./member.entity";

@Entity("cashouts")
export class Cashout {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: "member_id" })
  memberId: number;

  @ManyToOne(() => Member)
  @JoinColumn({ name: "member_id" })
  member: Member;

  @Column({ name: "account_id" })
  accountId: number;

  @ManyToOne(() => CashoutAccount)
  @JoinColumn({ name: "account_id" })
  account: CashoutAccount;

  @Column({ name: "debit_entry_id", nullable: true })
  debitEntryId: number | null;

  @ManyToOne(() => LedgerEntry, { nullable: true })
  @JoinColumn({ name: "debit_entry_id" })
  debitEntry: LedgerEntry | null;

  @Column({ name: "amount_cents" })
  amountCents: number;

  @Column({ type: "text", default: "pending" })
  status: string;
}
