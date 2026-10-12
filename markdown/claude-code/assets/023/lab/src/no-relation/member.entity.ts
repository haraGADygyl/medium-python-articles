import { Column, Entity, PrimaryGeneratedColumn } from "typeorm";

@Entity("members")
export class Member {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ type: "text", unique: true })
  email: string;
}
