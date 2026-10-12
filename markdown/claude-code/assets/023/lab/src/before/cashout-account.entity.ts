import { Column, Entity, JoinColumn, ManyToOne, PrimaryGeneratedColumn } from "typeorm";
import { Member } from "./member.entity";

@Entity("cashout_accounts")
export class CashoutAccount {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: "member_id" })
  memberId: number;

  @ManyToOne(() => Member)
  @JoinColumn({ name: "member_id" })
  member: Member;

  @Column({ type: "text", name: "iban_last4" })
  ibanLast4: string;
}
