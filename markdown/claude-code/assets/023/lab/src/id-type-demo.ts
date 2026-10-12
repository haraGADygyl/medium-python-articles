import { DataSource } from "typeorm";
import dataSource from "./data-source";

// Load the same cashout row through the "before" and the "after" entities.
async function loadWith(entitySet: string): Promise<void> {
  const { Cashout } = await import(`./${entitySet}/cashout.entity`);
  const scoped = new DataSource({
    ...dataSource.options,
    entities: [`${__dirname}/${entitySet}/*.entity.ts`],
  } as typeof dataSource.options);
  await scoped.initialize();
  const row = await scoped.getRepository(Cashout).findOneByOrFail({ amountCents: 2500 });
  console.log(`${entitySet}: id=${JSON.stringify(row.id)} memberId=${JSON.stringify(row.memberId)}`);
  await scoped.destroy();
}

async function main(): Promise<void> {
  await loadWith("before");
  await loadWith("after");
}

main();
