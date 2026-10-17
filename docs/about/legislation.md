# Principles for Strong Data-Broker Privacy Legislation

> **This is not legal advice, and it is not model legislation.** No one involved in this document is acting as your attorney. It is an advocacy resource: a plain-language guide to what strong data-broker privacy legislation should accomplish, the loopholes that weaken it, and starting points for conversation with lawmakers and counsel. Any "illustrative language" below is a non-binding conversation starter, **not** statutory text to adopt as-is — real bills must be drafted and reviewed by qualified legislative counsel. Consult a licensed attorney and your jurisdiction's legislative drafting office before relying on anything here.

---

## Purpose

The README for this project argues that the real fix for the data-broker problem is not software but law, and asks libraries and advocates to push for it. This document exists so that "push for legislation" is not an empty phrase. It gives a concrete sense of what to ask for and what to watch out for.

**Who this is for:** primarily someone with a legal or policy background who wants to contribute suggestions and guidance — whether in plain language or by proposing example verbiage that might belong in a bill. It is also for the advocate or library association walking into a legislator's office who needs to know what "good" looks like.

**Scope — private entities.** This document focuses on **private data brokers and the commercial collection and sale of personal information.** It deliberately does *not* take on government or law-enforcement surveillance. That is a real and serious problem, but it is a separate fight and a separate bill.

It is deliberately **principles-first**. It does not try to reinvent the detailed statutory work that privacy experts and legislative counsel already do; instead it points to that work (see [References](#references-real-laws-and-model-bills)) and focuses on goals and pitfalls that can be carried into the conversation.

---

## What strong legislation should accomplish (the "dos")

1. **Make deletion the default, and make it stick.** People should be able to require a broker to delete their information and *keep* it deleted — not re-acquire and re-list it weeks later from a "new" source. Weak laws allow a delete-then-recollect cycle; strong laws bar re-collection after a deletion request absent fresh, genuine consent.

2. **Provide a single, universal, free, one-step opt-out.** One federal portal, modeled on the FTC's **National Do Not Call Registry** (donotcall.gov): a person submits their information once, and *all* covered brokers must delete it and honor an ongoing bar on re-collection — no filing hundreds of separate requests, no fee, no "premium" tier. California's **DELETE Act** (SB 362) is the state-level version and shows it can be built.

3. **Put the burden on the broker, not the person.** The default should be that collecting and selling personal information requires meaningful opt-*in* consent, not that individuals must discover and chase down every broker to opt *out*.

4. **Shrink what counts as "publicly available."** Brokers' single biggest excuse is that information is "publicly available." Several state privacy laws already define the term narrowly — limited to government records and a few defined categories — and notably do *not* treat everything posted online as public (see Colorado's CPA, Virginia's VCDPA, and California's definitions, several of which exclude data a consumer restricted to a specific audience). Tightening this definition, and treating aggregated or enhanced data as no longer "public," directly shrinks what brokers can lawfully scrape and sell.
   - *Optional / reach (a harder, separate fight):* define "social-media platform" in statute and require all data for users **under 18** to be private by default with no public option, and public sharing for users **18 and over** to be opt-in, never default. Precedent exists for the minors half (COPPA already mandates heightened defaults for children's data), though platform-design mandates are a bigger lift than the definitional fix and may belong in their own bill.

5. **Define "personal information" and "data broker" broadly.** Cover names, addresses, phone numbers, relatives, location history, inferences, and derived/aggregated data — and cover any entity trading in it, however it labels itself.

6. **Reach any entity handling a covered person's data — foreign or domestic.** The law should apply based on *whose data is processed*, not where the company sits (as GDPR and CCPA already do), so a broker can't escape by incorporating or hosting overseas. Two honest hard parts follow:
   - **Collection is the real challenge, not jurisdiction.** A penalty you can't collect from a company with no US assets is theater. The workable levers are indirect: bar non-compliant foreign brokers from the US market, hold their US-based partners, customers, and payment processors liable for dealing with them, and restrict data *transfers* to jurisdictions without adequate protection (GDPR's "adequacy" model).
   - **Foreign-adversary data harvesting is a related but separate track.** A hostile state acquiring Americans' bulk data is largely handled through national-security tools (CFIUS, export-style transfer restrictions), not consumer-privacy law — but cutting off collection and sale at the source shrinks that inventory too. This bill's job is the supply; point to the national-security track for the buyer-specific piece.

7. **Provide real enforcement with teeth** — not an under-funded agency that sends a sternly worded letter. Four levers, which work best together:
   - **Government enforcement as the primary path.** People shouldn't have to hire a lawyer to vindicate their rights — the law should establish, or expressly expand and fund, a dedicated state or federal body (or empower a state AG) to receive, investigate, and act on violations on the public's behalf. This is the main enforcer, and it handles the pattern-and-practice cases no individual could bring alone.
   - **A private right of action as the backstop.** But enforcement can't depend *entirely* on an agency choosing to act, because agencies get captured, defunded, or overwhelmed. Individuals must retain the right to sue (with meaningful statutory damages) so their rights don't switch off the day the enforcer goes quiet. This is precisely the provision industry fights hardest — an agency can be pressured; millions of potential plaintiffs cannot.
   - **Penalties calculated to actually deter, with a non-negotiable floor.** Not flat fines (the cost of doing business) but a percentage of annual revenue — for reference, the GDPR caps at 4% of global turnover — assessed across the **whole corporate family** (so the business can't hide in a subsidiary) and accruing **per affected person, not per incident**. And the statutory minimum should not be settle-able down to a token sum: a company that broke the law and can't survive the penalty is not too big to fail, it failed.
   - **A heightened multiplier for minors' data** — minors need no separate regime (they're already covered), but because they can't meaningfully consent and profiling them causes greater harm, violations involving a minor's information should carry an increased penalty.

8. **Require transparency, provenance, and a downstream deletion chain.** Brokers should have to disclose what they hold about a person, where they got it, and to whom they've sold it. But disclosure alone isn't enough — deletion has to *travel*:
   - **The broker must propagate the deletion order.** When a person's data is deleted, the broker is responsible for notifying every downstream buyer it sold that information to that the data must also be deleted — the obligation follows the data, it doesn't stop at the first seller.
   - **Everyone must confirm deletion back to the person.** The broker and every downstream recipient must report back to the data owner once they have actually deleted the data from their systems, with a timestamp — so the person has proof it's gone, not just a promise. Without a confirmation requirement, "we deleted it" is unverifiable and unenforceable.

9. **Stay ahead of the AI curve.** See the dedicated section below — this is the area most current laws neglect.

10. **Cover sensitive categories — but don't break legitimate use.** Location, health, biometric, and immigration-status data cause concrete physical harm (stalking, surveillance, targeting of vulnerable people) and warrant the strongest protection. The target of this document is the **commercial sale and brokerage** of that data, *not* the legitimate operational uses it must still serve. Two carve-outs matter:
   - **Legitimate operational sharing must survive.** A hospital sharing health or biometric data for treatment, care coordination, or other bona fide medical operations is categorically different from a broker selling it. The law must stop the sale without breaking the care.
   - **Safety uses must survive — but narrowly, and not as a surveillance backdoor.** Some exposure of data is necessary to keep people safe: protective-order systems, domestic-violence shelters coordinating to protect a survivor, or a genuine life-threatening emergency. But "safety" and "imminent threat" are exactly the elastic phrases that get stretched into broad, warrantless access, so the carve-out must be written with guardrails, not just good intentions:
     - **Oriented to protecting the person, not investigating them.** The exception should serve the individual whose data it is (or a specific person in genuine, immediate danger) — not general investigative or intelligence access.
     - **Government access still requires legal process.** This carve-out must *not* become a route for law enforcement or agencies to obtain what a warrant or court order would otherwise require. Any narrow emergency exception should be limited to imminent danger to life, reviewable by a court after the fact — mirroring existing exigent-circumstances standards, not inventing a looser one.
     - **Logged and auditable.** Every invocation of the safety carve-out should be recorded and subject to audit, so it cannot operate invisibly or become a standing pipeline.

     Written this way, the carve-out protects victims without becoming a shield for an abuser or a workaround for surveillance. (Government surveillance writ large is a separate fight — see Scope — but because this risk lives *inside* a provision this bill would contain, the bill has to close it here.)

   The through-line: prohibit **selling and trading** sensitive data as a commodity; preserve **using** it for care and safety.

---

## Loopholes to watch for (the "don'ts")

- **The "publicly available information" carve-out.** Brokers argue that data scraped from public records or social media is exempt. This swallows the rule. Most broker data is assembled from "public" sources. Strong laws both narrow the definition (see principle 4 above) and treat aggregated or enhanced data as no longer "public."
- **Delete-then-recollect.** A deletion right with no bar on re-acquisition is theater; the broker simply re-buys the same record next quarter.
- **Fee-gated or multi-step opt-outs.** Any process that costs money, requires an account, or must be repeated per-broker is designed to have low completion.
- **Narrow definitions.** If "data broker" is defined so tightly that firms can restructure to avoid the label, the law is toothless.
- **Preemption without a floor.** A federal law that *overrides* stronger state laws while providing weaker protection is a net loss. Watch for industry-backed "privacy" bills whose main function is preemption.
- **Fixed-dollar fines.** A flat penalty is an operating expense to a large broker, not a deterrent. If the fine is smaller than the profit from the violation, the law is a price list. Revenue-based penalties (see the enforcement principle above) are the fix.
- **Subsidiary/affiliate revenue-hiding.** A revenue-based penalty assessed only against the specific entity charged invites companies to isolate the broker business in a small subsidiary while profits flow to the parent. Penalties should reach consolidated parent-and-subsidiary revenue.
- **Self-regulation and voluntary registries.** "Industry will police itself" provisions reliably fail.
- **No enforcement path for individuals.** Rights with no private right of action depend entirely on an agency's willingness and budget to act — which is why the law should both grant a private right of action and name a properly funded enforcer (see principle 6 above).

---

## Staying ahead of the AI curve

Most existing privacy laws were written before large-scale AI training and do not address it. Legislation written today should, because a deletion right is hollow if the data has already been absorbed into a model that no opt-out reaches.

**Principles to push for:**

- **Consent to sell is not consent to train.** Using personal information to train AI/ML models should require its own explicit, separate opt-in — not be bundled into a broker's general terms.
- **A right to exclude your data from training sets.** People should be able to require that their information not be used to train models going forward.
- **A meaningful path to removal from existing models.** People should have a route to have their information removed from, or rendered non-identifying in, models already trained on it.
- **Provenance and disclosure for training data.** Entities training on broker-sourced data should have to disclose that, so rights can attach to it.

**An honest note on difficulty (do not let anyone paper over this).** "Delete my data from a model that's already trained" is, today, an unsolved problem — technically and legally. You generally cannot surgically extract one person's influence from a trained model without retraining or specialized (and immature) machine-unlearning techniques. Advocates should push for the *right* and for requirements that make it tractable (e.g. exclusion at training time, provenance tracking, retraining obligations on a schedule), while being clear-eyed that "just delete it from the model" is not a solved capability. A law that assumes it is will not survive contact with reality; a law that ignores AI training entirely will be obsolete on arrival. The goal is the difficult middle: enforceable forward-looking exclusion plus a genuine, technically-informed removal pathway.

---

## A call to law librarians (and other legally-trained readers)

This document is written by contributors who are **not** lawyers, and it shows — it stays at the level of principles on purpose.

**If you are a law librarian, a librarian with legal training, or a legal professional who shares these values, this is where your expertise is most needed.** Law librarians in particular sit at exactly the right intersection: fluent in legal research, embedded in the library-privacy tradition this project draws on, and skilled at finding and synthesizing the real statutes, model bills, and scholarship that a document like this should rest on.

Contributions we'd especially welcome, offered in that spirit and still **not as legal advice to any reader**:

- Sharper, better-sourced illustrative language for any principle above.
- Identification of the strongest existing statutes and model bills to point to.
- Flagging where our plain-language framing is legally imprecise or misleading.
- Analysis of the AI-training questions from a legal-doctrine perspective.
- Jurisdiction-specific notes (what a given state already has, where the gaps are).

Open an issue or pull request. Please keep contributions framed as general educational information and references, not as legal advice or attorney-client work — the goal is to make this resource *more* accurate and *better* anchored to real law, while it remains an advocacy guide rather than a substitute for counsel.

---

## Illustrative language (non-binding conversation starters)

> Reminder: the following are **plain-language sketches to illustrate intent**, not statutory text. They exist to make the principles concrete in conversation. Real provisions must be drafted by legislative counsel.

- *Deletion that sticks:* "Upon a verified deletion request, a data broker shall delete the individual's covered information and shall not re-collect, re-acquire, or re-list that information except upon the individual's subsequent affirmative, informed opt-in consent."
- *Downstream deletion chain:* "Upon deleting an individual's covered information, a data broker shall, within [X] days, notify every third party to which it sold, licensed, or transferred that information that the information must be deleted. The broker and each such third party shall confirm completion of the deletion to the individual, with the date of deletion, within [X] days."
- *Universal opt-out (one portal):* "The [Federal Trade Commission / State] shall maintain a free, publicly accessible registry through which an individual may submit a single deletion request; registration shall obligate all covered data brokers to delete that individual's covered information within [30] days and to honor the ongoing bar on re-collection." (Modeled on the National Do Not Call Registry and California's DELETE Act.)
- *Training consent:* "Consent to the collection or sale of covered information does not constitute consent to its use in training an automated model. Such use requires separate, express, opt-in consent."
- *Training exclusion:* "An individual may direct that their covered information not be used to train, fine-tune, or otherwise develop an automated model, and a covered entity shall exclude it from such use going forward."
- *Revenue-based penalty:* "A covered entity that violates this Act shall be subject to a civil penalty of not less than [X]% of the total annual revenue of the entity together with its parent, subsidiaries, and affiliated entities, calculated on a consolidated basis. Each affected individual shall constitute a separate violation." (The percentage is the central policy lever — set it high enough to deter, not to be budgeted for; per-person accrual keeps a mass exposure from counting as a single violation.)
- *Heightened penalty for minors:* "Where a violation involves the covered information of a minor, the applicable civil penalty shall be increased by a factor of [N]."
- *Sensitive data — prohibit sale, preserve use:* "A covered entity shall not sell, license, or trade sensitive covered information (including precise geolocation, health, biometric, and immigration-status information). Nothing in this section restricts the use or disclosure of such information for the provision of medical care, care coordination, or other bona fide operational purposes by the entities providing those services. Disclosure for safety purposes shall be limited to protecting the individual whose information it is, or a specific person in imminent danger of death or serious physical harm; access by a government entity shall require a warrant or court order except in such an imminent emergency, which shall be subject to after-the-fact judicial review, and every safety disclosure shall be logged and auditable."

Each of these has real drafting questions behind it (verification, scope, enforcement, interaction with other law) that only qualified counsel can resolve.

---

## References: real laws and model bills

**These are examples, not endorsements.** Citing a law here doesn't mean we support it or hold it up as a model — several below contain the very loopholes this document warns against. They're listed as real, studyable examples of how these questions have been approached; evaluate each against the principles above.

**And none of these frameworks is 100% correct.** Every one involves hard tradeoffs — privacy vs. free expression, the right to delete vs. the public interest in an accurate historical and journalistic record, strong protection vs. workable enforcement — and each has drawn legitimate criticism. Privacy law is genuinely difficult and reasonable people disagree in good faith; these principles are a direction to push, not a claim the answers are settled. That is exactly why legal and law-librarian input (see above) matters.

A non-exhaustive starting set to research (verify current status and text — laws change):

- **California** — CCPA/CPRA and California's **DELETE Act** (SB 362), which creates a centralized broker-deletion mechanism — the closest existing model to the "universal one-step opt-out" principle.
- **Other state comprehensive privacy acts** — e.g. Virginia (VCDPA), Colorado (CPA), Connecticut, and a growing list; compare their broker and deletion provisions and their exemptions.
- **Vermont and other state data-broker registration laws** — narrower, but establish the "data broker" definition and registration concept.
- **EU GDPR** — for the opt-in-by-default model, the right to erasure ("right to be forgotten"), and data-provenance/DPIA concepts.
- **Advocacy organizations' recommendations and analyses** — worth drawing from:
  - EFF, [Recommendations for Consumer Data Privacy Laws](https://www.eff.org/deeplinks/2019/06/effs-recommendations-consumer-data-privacy-laws) and its ongoing [data-broker coverage](https://www.eff.org/deeplinks/2025/08/data-brokers-are-ignoring-privacy-law-we-deserve-better).
  - EPIC (Electronic Privacy Information Center), [Data Brokers issue hub](https://epic.org/issues/consumer-privacy/data-brokers/) — legislation, testimony, and analysis.
  - ACLU, [consumer privacy / data-broker analysis](https://www.aclu.org/news/privacy-technology/senators-reveal-their-plans-to-protect-consumer-privacy-online) and state campaigns such as the ACLU of Massachusetts' [Data Privacy Now](https://www.aclum.org/campaigns-initiatives/data-privacy-now/).
  - Academic privacy scholars have published model language and critiques; a law librarian can help surface the current scholarship.

When in doubt, a **law librarian** or a legislature's own **legislative counsel / drafting office** is the right next stop — not this document.

---

*This resource supports the advocacy called for in the project [README](../README.md). It is maintained as a community document and will be stronger for expert contributions — especially from the legal and law-library communities — but it remains general information and advocacy guidance, not legal advice.*
