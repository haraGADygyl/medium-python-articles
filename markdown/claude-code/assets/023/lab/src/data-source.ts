import "reflect-metadata";
import { DataSource } from "typeorm";

// LAB_ENTITIES picks which entity folder TypeORM compares with the database.
const entitySet = process.env.LAB_ENTITIES ?? "after";

export default new DataSource({
  type: "postgres",
  host: "localhost",
  port: 55432,
  username: "lab",
  password: "lab",
  database: "cashouts",
  entities: [`${__dirname}/${entitySet}/*.entity.ts`],
  migrations: [
    `${__dirname}/migrations/*.ts`,
    // LAB_FIX=1 adds the forward-only migration that narrows the FK columns.
    ...(process.env.LAB_FIX === "1" ? [`${__dirname}/fix/*.ts`] : []),
  ],
});
