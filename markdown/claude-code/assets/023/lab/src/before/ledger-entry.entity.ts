import { Column, Entity, JoinColumn, ManyToOne, PrimaryGeneratedColumn } from "typeorm";
import { Member } from "./member.entity";

@Entity("ledger_entries")
export class LedgerEntry {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: "member_id" })
  memberId: number;

  @ManyToOne(() => Member)
  @JoinColumn({ name: "member_id" })
  member: Member;

  @Column({ name: "delta_cents" })
  deltaCents: number;
}
