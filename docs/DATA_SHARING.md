# Data sharing and aggregator-first opt-outs

## Who shares with whom

Every opt-out gets its own email address (`you+oo<random>@domain`; see [EMAIL_SETUP.md](EMAIL_SETUP.md)). Each address is given to exactly one broker or parent company. When mail reaches it from anyone else, that broker, or someone it works with, passed the address on.

**Admin → Data sharing** turns those records into "given to → mail came from" pairs:

| How sure | Evidence |
|---|---|
| Strong | 3 or more different opt-out addresses given to the broker reached the same company |
| Likely | 2 addresses |
| Possible | 1 address |
| Can't tell who | the mail came from a free email service (gmail.com, outlook.com…) |

The broker's own domains, its parent company, and the other sites in its family never count as sharing. OpenOptOut only looks at the sender's domain; it never reads or stores the message.

## Aggregators first

Some companies sell data in bulk to other brokers and people-search sites. Opting out of them first leaves less for the downstream sites to copy back. Each broker gets a weight from four sources:

- **Known data wholesalers**: Acxiom, LexisNexis, Epsilon, Experian and Equifax marketing, TransUnion/TLO, Data Axle, LiveRamp, CoreLogic, PeopleConnect (`backend/core/catalog/aggregators.json`, with sources)
- **Cascades**: opting out here is known to also remove another site (parent-company catalog)
- **Families**: sites that belong to a parent company with many sites
- **Observed sharing**: the edges above (strong 3, likely 2, possible 1)

The schedule's **Which brokers go first each day** setting defaults to **Aggregators first**. The order is aggregator weight, then broker priority, then age. **Data sharing** lists the ranking and the reasons for it. Choose "By priority" to go back to ordering by priority alone.
