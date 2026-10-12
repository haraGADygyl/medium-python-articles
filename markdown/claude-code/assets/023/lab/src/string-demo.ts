import dataSource from "./data-source";
import { Cashout } from "./after/cashout.entity";

// The same column, read raw and read through an entity.
async function main(): Promise<void> {
  await dataSource.initialize();
  const [raw] = await dataSource.query(
    "SELECT member_id FROM cashouts WHERE amount_cents = 2500",
  );
  const cashout = await dataSource
    .getRepository(Cashout)
    .findOneByOrFail({ amountCents: 2500 });
  console.log("raw row:", raw);
  console.log("entity: ", { memberId: cashout.memberId });
  await dataSource.destroy();
}

main();
