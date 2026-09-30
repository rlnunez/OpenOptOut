import { useEffect, useState } from 'react'
import {
  BookOpen, Shield, Mail, AlertTriangle, Plus,
  Edit3, Trash2, X, Check, ChevronDown, ChevronRight,
  ExternalLink, Info, Lightbulb, ShieldAlert
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { escapeHtml, renderLinks } from '../components/Markdown'

// ── Static documentation data ─────────────────────────────────────────────────

const STATIC_DOCS = {
  setup: [
    {
      id: 'how-it-works',
      title: 'How OpenOptOut works',
      content: `OpenOptOut automates the removal of your personal information from data brokers — companies that collect and sell your name, address, phone number, and other details without your direct consent.

**The pipeline has four stages:**

1. **Identity vault** — You enter all name variants, email addresses, phone numbers, and past/current addresses for each family member. More variants = better coverage.

2. **Discovery** — The system searches data broker sites for listings matching your identity data and logs which sites have your information.

3. **Opt-out** — For each confirmed listing, OpenOptOut submits a removal request using the broker's opt-out form or sends a formal email request. Every outgoing email includes a unique tracking ID in the subject line.

4. **Monitoring** — The email monitor polls your configured inbox for confirmation emails, matches them to your requests using the tracking ID, and marks removals as confirmed. Re-check dates are set automatically so removals are re-verified before brokers can re-list you.`,
    },
    {
      id: 'email-setup',
      title: 'Setting up your removal email',
      content: `We recommend creating a **dedicated email address** purely for data removal requests — keep it separate from your personal inbox.

**Why a dedicated address?**
- Brokers often add opt-out requesters to new marketing lists. A dedicated address contains any blowback.
- All confirmation emails land in one place, making the monitor's job simple.
- You can see at a glance whether a broker replied.

**Recommended setup (OAuth 2.0 — Most Secure):**
1. Create or use a dedicated mailbox (e.g. `yourname.removals@gmail.com` or Outlook).
2. In OpenOptOut Settings → Email (or during the initial Setup Wizard), click **Connect with Google** or **Connect with Microsoft**.
3. Authorize the requested mail permissions. OAuth uses temporary scoped tokens instead of storing long-lived passwords.

**Alternative setup (App Passwords / SMTP):**
If you use Yahoo, Fastmail, or prefer traditional IMAP/SMTP:
1. Enable 2-Step Verification on the account
2. Generate an App Password in your provider's security settings (e.g. `myaccount.google.com/apppasswords`)
3. In OpenOptOut Settings → Email, select your provider preset
4. Enter your email and paste the App Password (not your primary password) into the password fields
5. Click "Test connection" — both IMAP and SMTP should show green`,
    },
    {
      id: 'recheck-explained',
      title: 'Re-checks and why they matter',
      content: `A confirmed removal does not mean permanent removal. Data brokers continuously scrape public records, social media, and other data sources. Most re-list individuals within **30–90 days** of removal.

**How re-checks work:**
- When a removal is confirmed, a re-check date is set (default 90 days)
- On the re-check date, the removal is re-queued for re-submission
- If the broker complies again quickly, the cycle continues automatically

**Adjusting re-check intervals:**
Go to Settings → Scheduler → Recheck interval. Resistant brokers (those that frequently re-list) should be set to 30 days. Compliant ones can safely be left at 90.

**The Scheduled page** shows your upcoming and overdue re-checks. You can snooze individual ones (if you've manually verified the listing is still gone) or re-queue them immediately.`,
    },
,
    {
      id: 'database-scaling',
      title: 'Database scaling — SQLite vs PostgreSQL',
      content: `OpenOptOut defaults to SQLite for simplicity, but PostgreSQL is strongly recommended for institutional deployments with more than ~100 concurrent users.

**SQLite is fine for:**
- Library staff deployments (10–200 users)
- Personal/family use
- Testing and evaluation
- Single-instance deployments without high concurrency

**Switch to PostgreSQL when:**
- Deploying for library patrons (potentially thousands of users)
- More than ~500 total user accounts
- Running the opt-out scheduler on a busy instance
- Need for connection pooling across multiple app instances
- High availability or read replicas required

**Harris County example:**
Harris County Public Library serves 4.7 million residents across 26 branches. A patron-facing deployment could have 50,000+ registered users. At that scale:
- SQLite would show "database locked" errors under concurrent opt-out runs
- PostgreSQL handles thousands of concurrent connections cleanly
- Connection pooling (PgBouncer) is recommended above 200 concurrent users

**Migration:**
Go to Admin → Database → "Migrate to PostgreSQL". The tool copies all data table-by-table with full integrity preservation. Run during off-hours and keep the SQLite backup for 30 days.

**Recommended Postgres providers:**
- **Supabase** (free tier, easy setup) — supabase.com
- **Railway** ($5/month, one-click Postgres) — railway.app
- **Neon** (serverless Postgres, generous free tier) — neon.tech
- **Amazon RDS** (enterprise, with automated backups and encryption)
- **Self-hosted** on the same Docker host with a postgres container`,
    },
    {
      id: 'postgres-setup',
      title: 'PostgreSQL setup guide',
      content: `**Option 1 — Add Postgres to your Docker Compose:**

Add this to your docker-compose.yml:

\`\`\`yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: openoptout
      POSTGRES_USER: ps_user
      POSTGRES_PASSWORD: your-strong-password
    volumes:
      - pg_data:/var/lib/postgresql/data
    restart: unless-stopped

  api:
    environment:
      - DATABASE_URL=postgresql://ps_user:your-strong-password@db:5432/openoptout

volumes:
  pg_data:
\`\`\`

**Option 2 — Managed Postgres (Supabase example):**

1. Create a project at supabase.com
2. Go to Settings → Database → Connection string
3. Copy the URI (starts with postgresql://)
4. Set DATABASE_URL in your .env file
5. Restart the container

**Option 3 — Neon (serverless, scales to zero):**

1. Create a project at neon.tech
2. Copy the connection string from the dashboard
3. Set DATABASE_URL in your .env file

**After changing DATABASE_URL:**
If migrating from SQLite, use the migration tool in Admin → Database first.
If starting fresh, just set the URL and restart — the schema is created automatically.`,
    },
,
    {
      id: 'db-enterprise-auth',
      title: 'Enterprise database authentication',
      content: `For deployments where a plain username/password connection string is not acceptable, OpenOptOut supports several PostgreSQL authentication methods configurable under Admin → Database → Connection.

**Security principle:**
Secrets (passwords, private keys, certificates) are never stored in the application database or settings. They live in environment variables or mounted files that your database administrator controls. The app only reads them — it never writes, displays, or logs them.

**Supported methods:**

- **Password (SCRAM-SHA-256)** — standard auth. Combine with an SSL mode to encrypt in transit.
- **Password over verified TLS** — password auth with full certificate verification (sslmode=verify-full).
- **Client certificate (mutual TLS)** — the strongest common method. The client presents a certificate; no password is transmitted at all. Requires a CA cert, client cert, and client private key mounted as files.
- **Client certificate + password** — requires both, for high-security environments (finance, healthcare, government).
- **AWS RDS IAM** — short-lived (15-minute) tokens instead of a static password. Requires an IAM role and boto3.
- **GCP Cloud SQL IAM** — OAuth2 tokens from a service account. Requires google-auth.
- **Azure AD** — access tokens via managed identity. Requires azure-identity.
- **Kerberos / GSSAPI** — enterprise single sign-on using the ticket cache. Common in Active Directory environments.

**Where secrets go:**

| Material | Location |
|---|---|
| Password | DB_PASSWORD env var, or DB_PASSWORD_FILE (Docker/K8s secret) |
| CA certificate | Mounted file, path set in the UI |
| Client cert | Mounted file, path set in the UI |
| Client private key | Mounted file, chmod 600, owned by app user |
| Cloud IAM | IAM role / service account / managed identity (no static secret) |

**Mounting certificates in Docker Compose:**

Add to the api service:
\`\`\`yaml
volumes:
  - /host/certs/ca.pem:/certs/ca.pem:ro
  - /host/certs/client-cert.pem:/certs/client-cert.pem:ro
  - /host/certs/client-key.pem:/certs/client-key.pem:ro
secrets:
  - db_password
\`\`\`

Then set the file paths in the Connection config UI, and set DB_PASSWORD_FILE=/run/secrets/db_password.

**Cloud IAM dependencies** are optional — install only what you need:
\`\`\`
pip install -r requirements-cloud.txt
\`\`\`

Client-certificate auth with sslmode=verify-full is recommended for the highest security — no password is ever transmitted or stored, and both the client and server verify each other's identity.`,
    },
,
    {
      id: 'bot-evasion',
      title: 'Avoiding broker blocking',
      content: `Data brokers increasingly detect and block automated form submissions. OpenOptOut includes several measures to reduce blocking, configurable under Settings → Automation.

**User-agent rotation:**
Each broker submission uses a randomized browser fingerprint from a pool of ~15 current, real user agents (Chrome, Firefox, Safari, Edge across Windows and macOS). The viewport is matched to the platform so the browser context is internally consistent. Admins can add custom user-agent strings to expand the pool.

**Honest limitations:**
User-agent rotation is one layer, not a complete solution. Sophisticated brokers also fingerprint:
- TLS handshake signatures
- Canvas and WebGL rendering
- Request timing patterns
- Mouse movement and interaction

Rotation is most effective against simple UA-based blocking. It meaningfully raises the bar but does not defeat advanced bot-detection systems like those from Cloudflare or PerimeterX.

**Submission timing:**
The delay between submissions (default 1.5 seconds) makes traffic look less automated. Increasing it to 3–5 seconds reduces the chance of rate-limit blocks at the cost of slower throughput.

**Spreading out jobs:**
Rather than sending all opt-outs in one nightly burst — which creates an obvious traffic spike — you can spread them out (Settings → Scheduler):

- **Burst** — all at once at the run time (simplest, most detectable)
- **Time window** — spread evenly across a window like 10pm–6am
- **Rate limited** — a fixed number per hour, continuously
- **Distributed** — small batches spread across 24 hours (least detectable)

For a large deployment (e.g. a library serving thousands of patrons), distributed or rate-limited mode is strongly recommended. A nightly burst of thousands of submissions from one IP is both easy to detect and likely to overwhelm the container.

**Daily caps per person (spreads a new signup over days):**
A new member can have hundreds of pending opt-outs. Rather than firing all of them at once — a screaming automation signal — the scheduler caps how many brokers are submitted per member per day (Settings → Scheduler → *max opt-outs per day*, default 20), with a global system ceiling on top, whichever is reached first. A single member's pending brokers then clear gradually over weeks, which both looks far more human and protects your shared proxy pool. Individual members can be given a higher or lower cap for special cases (Scheduled → per-member config). Within each day's budget, brokers are dispatched **highest-priority-first** (a 1–5 priority per broker, 5 = highest). New brokers get a sensible auto-priority (property/resistant brokers rank highest), and a super admin can override it — per broker, in bulk, or with rules ("all property brokers = 5") — on the **Broker priority** admin page, and share those priorities between deployments via export/import. So a person's most sensitive exposures clear earliest.

**IP masking (the most effective measure):**
Brokers track and block primarily by IP address. A datacenter IP (what your server likely has) is the biggest tell. Configure proxies under Settings → Proxy:

- **Single proxy** — all traffic exits one IP
- **Rotating pool** — a different IP per broker, the strongest configuration

Residential proxies (real home ISP IPs) work far better than datacenter proxies or VPNs, which brokers block easily. Reputable providers include Bright Data, Oxylabs, Smartproxy/Decodo, and IPRoyal — the app has presets for each. Proxy credentials are read only from environment variables or mounted files, never stored in the app.

Use the "Test proxy" button to confirm your traffic is actually exiting through the proxy IP before running a batch.

**Recommended stack for a large deployment:**
Rotating residential proxy pool + user-agent rotation + distributed job spreading + 3–5 second submission delays. This combination looks very much like ordinary human traffic. Prioritize email-based opt-outs over form submissions for the most aggressive brokers.`,
    },
    {
      id: 'proxy-vpn-providers',
      title: 'Proxy & VPN provider recommendations',
      content: `There are two distinct needs here, and they call for different tools. **Proxies** mask the IP of the automation engine so brokers don't block your opt-out submissions. **VPNs** protect the privacy of an individual person's everyday browsing. Don't confuse the two — a consumer VPN is a poor fit for the automation engine, and a datacenter proxy does nothing for personal privacy.

These are informational recommendations to help you evaluate options, not endorsements. Pricing, ownership, and policies change — verify current details and read the provider's own terms before committing. Neither OpenOptOut nor its maintainers are affiliated with any provider below.

*Last reviewed: July 2026. Provider pricing, ownership, and policies change frequently — re-verify before relying on any detail here.*

---

**PART 1 — Residential proxy providers (for the automation engine)**

For submitting opt-outs at scale, residential proxies are the effective choice. They route through real home-ISP IP addresses, so submissions look like an ordinary person. The app has built-in presets for the first four.

The single most important thing to check is **how the provider sources its IPs.** Ethical providers get explicit, informed consent from the people whose connections form the network (usually by paying them or bundling it into an app with a clear opt-in). Unethical ones acquire IPs through malware or hidden SDKs. Since you're routing opt-out traffic through these IPs, sourcing integrity is both an ethical and a reputational matter for your institution.

- **Bright Data** — the largest residential network, with detailed compliance documentation and a published KYC process for customers. Enterprise-oriented, with granular geo-targeting. Higher price point; extensive controls. Has an app preset.
- **Oxylabs** — enterprise-grade, strong compliance posture, good support and documentation. Similar tier to Bright Data. Has an app preset.
- **Smartproxy / Decodo** — mid-market, more approachable pricing and a simpler dashboard. A common starting point for smaller deployments. Has an app preset.
- **IPRoyal** — budget-friendly, pay-as-you-go options, sources IPs through its "Pawns" app where users are paid and opt in. Has an app preset.
- **SOAX** — clean-IP focus with granular geo and consent-based sourcing. Well regarded; configure via the generic preset.

**Practical notes for proxies:**
- Match the proxy's geography to the residents you serve — U.S. brokers respond best to U.S. residential IPs, and some behave differently by region.
- Choose *rotating* residential endpoints for pool mode, or *sticky sessions* if a broker's flow needs the same IP across several page loads.
- Residential proxies are billed by bandwidth, not by request. Opt-out forms are light, so usage is typically modest, but monitor it on the provider dashboard.
- Always use the "Test proxy" button first to confirm your exit IP, then run a small batch before scaling up.

**What to avoid for the automation engine:** free proxy lists (often malware-sourced or logging your traffic), most datacenter proxies (brokers block these ranges wholesale), and consumer VPNs (shared exit IPs that are widely flagged).

---

**PART 2 — VPN providers (for individual privacy)**

A VPN is the right tool for a *person* who wants to reduce tracking of their own browsing, hide their IP from the sites they visit, and encrypt traffic on untrusted networks (library Wi-Fi, hotels, airports). It is not what the automation engine uses, but patrons and staff often ask what to use personally, so it's worth having recommendations on hand.

When evaluating a VPN, the things that actually matter for privacy are: an **independently audited no-logs policy**, ownership and jurisdiction you're comfortable with, modern protocols (WireGuard/OpenVPN), and a sustainable business model — if it's free, your data is usually the product.

- **Mullvad** — widely regarded as a privacy gold standard. Flat €5/month, accepts cash and anonymous account numbers (no email required), no personal info collected, independently audited. Based in Sweden.
- **Proton VPN** — from the makers of Proton Mail, audited no-logs policy, strong transparency, and a genuinely usable free tier (rare among trustworthy providers). Based in Switzerland; open-source apps.
- **IVPN** — privacy-first, audited, minimal data collection, anonymous account IDs. Transparent ownership. A strong Mullvad alternative.
- **Windscribe** — flexible, with a capable free tier; good for lighter needs. Read their logging policy to confirm it fits your threshold.

**Free-tier caveat:** Proton VPN and Windscribe offer legitimate free tiers. Be cautious with *other* free VPNs — many monetize by logging and selling browsing data, which is the opposite of what someone seeking privacy wants. "Free" and "private" rarely coexist unless a trustworthy paid product is subsidizing the free tier.

**For a library context:** Mullvad and Proton VPN are the easiest to recommend to patrons — Mullvad for its no-account-required model, Proton for its usable free tier and name recognition. Both let a person try the service without handing over personal information, which is itself a privacy win.

---

**One-line summary:** use *residential proxies* (Bright Data, Oxylabs, Smartproxy/Decodo, IPRoyal, SOAX) for the opt-out automation, and recommend *audited no-logs VPNs* (Mullvad, Proton VPN, IVPN) to individuals for their personal browsing privacy.`,
    },
  ],
  resistant: [
    {
      id: 'epsilon-guide',
      title: 'Epsilon — email opt-out (resistant)',
      content: `Epsilon is one of the largest upstream data brokers, supplying data to hundreds of smaller sites. Removing from Epsilon can cause your information to disappear from many downstream sites automatically.

**Required: email opt-out (not a web form)**

Send to **all three** of these addresses in the same email:
- \`optout@epsilon.com\`
- \`abacusoptout@epsilon.com\`
- \`dataoptout1@epsilon.com\`

**Subject line:** \`Data Removal Request — [Your Full Name]\`

**Body should include:**
- Full name (and any variants/maiden names)
- Current mailing address
- Any previous addresses from the last 5 years
- Statement: *"Please remove all personal data associated with me from your databases and do not sell or share my information with any third parties."*

**Timeline:** 4–6 weeks. Follow up if no response after 30 days. If you're in California, add: *"I am exercising my rights under the California Consumer Privacy Act (CCPA), Cal. Civ. Code § 1798.105."*

**Note:** Epsilon owns multiple brands. One email covers Epsilon Data Management, Abacus, FloSports data, and several others.`,
    },
    {
      id: 'ekata-guide',
      title: 'Ekata (TransUnion) — resistant',
      content: `Ekata is a business-focused identity verification service, now owned by TransUnion. They primarily serve other businesses rather than consumers, which makes consumer opt-outs slow and inconsistent.

**Steps:**
1. Email \`privacy@ekata.com\` with subject: \`Personal Data Removal Request\`
2. Include your full name, address, and phone number
3. Reference the CCPA (if applicable): *"Pursuant to CCPA Cal. Civ. Code § 1798.105, I request deletion of all personal data you hold about me."*
4. CC \`privacyrequests@transunion.com\` as Ekata is now a TransUnion entity

**Expected timeline:** 6–8 weeks. Ekata is required to respond within 45 days under CCPA.

**If no response:** File a complaint with the California Attorney General's office at oag.ca.gov/privacy/ccpa if you're a California resident. This often prompts action.`,
    },
    {
      id: 'sheerid-guide',
      title: 'SheerID — resistant',
      content: `SheerID is a verification platform used by businesses to verify military, student, and other status. They hold personal data but are resistant to consumer removal requests because their customers (not consumers) are their primary relationship.

**Steps:**
1. Go to \`sheerid.com/privacy-policy\` and scroll to "Your Privacy Rights"
2. Submit a deletion request via their online form
3. Also email \`privacy@sheerid.com\` with the same request
4. Include: full name, email addresses, any SheerID-verified programs you've used

**Important:** SheerID data often enters their system through their business customers (e.g. a retailer you bought from). You may also need to contact those retailers separately.

**If they don't respond:** SheerID is subject to GDPR if you're an EU resident and CCPA if you're a California resident. Cite the relevant regulation and request a response within the legally required timeframe.`,
    },
    {
      id: 'contactout-guide',
      title: 'ContactOut — resistant',
      content: `ContactOut aggregates professional contact information (work emails, LinkedIn profiles, phone numbers) and sells access to recruiters. They are particularly resistant because their paying customers depend on this data.

**Steps:**
1. Visit \`contactout.com/optout\` — search for yourself and submit removal
2. Also email \`support@contactout.com\` referencing your submission
3. If you have a LinkedIn profile, making it private reduces ContactOut's ability to re-scrape you

**Important:** ContactOut re-scrapes LinkedIn regularly. Even after removal, a public LinkedIn profile may cause re-listing within weeks. Consider making your LinkedIn contact information private or using LinkedIn's own data control settings.

**GDPR note:** ContactOut is based in San Francisco but serves EU clients. EU residents can invoke GDPR Article 17 (right to erasure) for stronger legal footing.`,
    },
    {
      id: 'peopleconnect-guide',
      title: 'PeopleConnect network — one opt-out for many',
      content: `PeopleConnect owns a large network of background check and people-search sites. A single suppression request at their central portal covers all of them.

**Sites covered by one opt-out:**
Intelius, TruthFinder, Instant Checkmate, US Search, Classmates.com, ZabaSearch, AnyWho, Addresses.com, PublicRecords.com, PeopleLookup, DateCheck, Spock, and more.

**How to opt out:**
1. Go to \`suppression.peopleconnect.us/login\`
2. Create an account (use your dedicated removals email)
3. Submit a suppression request for each family member separately
4. You will need to verify via email for each request

**Timeline:** 72 hours to 2 weeks depending on the site.

**Important:** You need to submit a separate request for each name variant and each historical address that appears in their systems. Run a search first to find all your listings.`,
    },
    {
      id: 'mylife-guide',
      title: 'MyLife — difficult, requires phone call',
      content: `MyLife is one of the most difficult brokers to remove from. They have a history of deceptive practices (including an FTC action) and often require multiple attempts.

**Method 1 — Phone (most reliable):**
Call **(888) 704-1900**, press 2. Ask to be removed from MyLife and Wink.com. Have ready:
- Your full name and any aliases
- Date of birth
- Current and one previous mailing address
- Email address on their site

**Method 2 — Email:**
Email \`privacy@mylife.com\` and \`removalrequests@mylife.com\` with your listing URL(s).

**Do not** create an account or pay for a report — this gives them more data and complicates removal.

**Timeline:** 7–14 days. Check back after 2 weeks and repeat if still listed.

**Persistence pays:** MyLife is known to re-list people. Add it to your 30-day re-check list rather than 90-day.`,
    },
  ],
  general: [
    {
      id: 'ccpa-template',
      title: 'CCPA deletion request template',
      content: `If you are a California resident, the California Consumer Privacy Act (CCPA) gives you the right to request deletion of your personal data from any business that collects it.

**Use this template for resistant vendors:**

---

Subject: CCPA Data Deletion Request — [Your Full Name]

To Whom It May Concern,

I am a California resident exercising my rights under the California Consumer Privacy Act (Cal. Civ. Code § 1798.105) to request the deletion of all personal information you have collected about me.

Please delete the following data associated with my identity:
- Full name: [Your Name]
- Address: [Your Address]
- Email: [Your Email]
- Phone: [Your Phone]

I request confirmation of deletion within 45 days as required by law. If you require additional verification of my identity, please contact me at the email address above.

[Your Name]
[Date]

---

**For EU residents:** Replace the CCPA citation with: *"I am exercising my rights under GDPR Article 17 (Right to Erasure). Please confirm deletion within 30 days."*`,
    },
    {
      id: 'upstream-strategy',
      title: 'The upstream strategy — remove from the source',
      content: `Many smaller data broker sites don't collect data themselves — they purchase it from a handful of large upstream suppliers. If you remove yourself from the sources, you can trigger automatic removal from dozens of downstream sites.

**The key upstream brokers to prioritize:**

1. **Acxiom** (\`isapps.acxiom.com/optout/optout.aspx\`) — one of the largest. Data from Acxiom flows to hundreds of sites.

2. **Epsilon** — see the Epsilon guide. Covers many marketing databases.

3. **Data Axle** (formerly InfoUSA/Infogroup) — email \`privacy@data-axle.com\`

4. **LexisNexis** (\`consumer.risk.lexisnexis.com/request\`) — major supplier to background check services.

5. **Equifax, Experian, TransUnion** (marketing files, not credit files) — opt out at \`optoutprescreen.com\` to stop pre-screened credit offers, plus each bureau's own marketing opt-out.

**Timing:** Remove from upstream sources first, then wait 2–3 weeks before submitting downstream requests. Many downstream sites auto-refresh their data — if the source is clean, they may clear automatically.`,
    },
  ],
}

// ── Markdown renderer (simple subset) ────────────────────────────────────────

function SimpleMarkdown({ content }) {
  const lines = content.split('\n')
  return (
    <div className="space-y-2 text-slate-300 text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />

        // headings
        if (line.startsWith('**') && line.endsWith('**') && !line.slice(2,-2).includes('**'))
          return <p key={i} className="text-white font-medium mt-3">{line.slice(2,-2)}</p>

        // horizontal rule
        if (line.trim() === '---')
          return <hr key={i} className="border-slate-700 my-3" />

        // bullet points
        if (line.startsWith('- ') || line.startsWith('* '))
          return (
            <div key={i} className="flex gap-2 ml-2">
              <span className="text-slate-600 mt-1 shrink-0">•</span>
              <span dangerouslySetInnerHTML={{ __html: renderInline(line.slice(2)) }} />
            </div>
          )

        // numbered list
        if (/^\d+\.\s/.test(line)) {
          const [num, ...rest] = line.split('. ')
          return (
            <div key={i} className="flex gap-2 ml-2">
              <span className="text-slate-500 shrink-0 font-mono text-xs mt-0.5">{num}.</span>
              <span dangerouslySetInnerHTML={{ __html: renderInline(rest.join('. ')) }} />
            </div>
          )
        }

        return <p key={i} dangerouslySetInnerHTML={{ __html: renderInline(line) }} />
      })}
    </div>
  )
}

// Escapes first: this renders admin-editable notes that every signed-in user
// sees, so the content must never be able to inject markup or script links.
function renderInline(text) {
  return renderLinks(escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-medium">$1</strong>')
    .replace(/`(.+?)`/g, '<code class="bg-slate-700 px-1 py-0.5 rounded text-xs text-slate-200 font-mono">$1</code>'))
}

// ── Accordion item ────────────────────────────────────────────────────────────

function DocItem({ item, isAdmin, onEdit, onDelete }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-slate-700/50 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/50 transition-colors text-left">
        <span className="text-slate-200 text-sm font-medium">{item.title}</span>
        <div className="flex items-center gap-2">
          {isAdmin && item._custom && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
              <button onClick={e => { e.stopPropagation(); onEdit(item) }}
                className="p-1 text-slate-500 hover:text-shield-400 transition-colors"><Edit3 size={12} /></button>
              <button onClick={e => { e.stopPropagation(); onDelete(item.id) }}
                className="p-1 text-slate-500 hover:text-red-400 transition-colors"><Trash2 size={12} /></button>
            </div>
          )}
          {open ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-700/30 group">
          <SimpleMarkdown content={item.content} />
          {item.updated_by && (
            <p className="text-slate-600 text-xs mt-3">
              Last updated by {item.updated_by} · {new Date(item.updated_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Note editor modal ─────────────────────────────────────────────────────────

function NoteModal({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(initial || { title: '', content: '', section: 'general' })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  const save = async () => {
    if (!form.title.trim() || !form.content.trim()) { setError('Title and content are required'); return }
    setSaving(true); setError('')
    try {
      const { data } = initial
        ? await api.patch(`/help/notes/${initial.id}`, form)
        : await api.post('/help/notes', form)
      onSaved(data); onClose()
    } catch (e) {
      setError(e.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl p-6 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">{initial ? 'Edit note' : 'Add custom note'}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        <div className="space-y-3 flex-1 overflow-y-auto">
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Title</label>
            <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
              placeholder="e.g. How to opt out of Acxiom" autoFocus
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500" />
          </div>
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Section</label>
            <select value={form.section} onChange={e => setForm(f => ({...f, section: e.target.value}))}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none">
              <option value="general">General</option>
              <option value="resistant">Resistant vendors</option>
              <option value="setup">Setup & configuration</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="text-slate-400 text-xs mb-1 block">Content (Markdown supported)</label>
            <textarea value={form.content} onChange={e => setForm(f => ({...f, content: e.target.value}))}
              rows={12} placeholder="Write your documentation here. **Bold**, `code`, [links](url), and bullet lists are supported."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500 font-mono resize-none" />
          </div>
        </div>
        <div className="flex gap-2 pt-4">
          <button onClick={onClose} className="flex-1 py-2 border border-slate-700 rounded-lg text-slate-400 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
          <button onClick={save} disabled={saving}
            className="flex-1 py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
            {saving ? 'Saving…' : initial ? 'Save changes' : 'Add note'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Section panel ─────────────────────────────────────────────────────────────

function DocSection({ icon: Icon, title, description, items, isAdmin, onEdit, onDelete, color = 'text-shield-400' }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2.5 mb-3">
        <Icon size={16} className={color} />
        <div>
          <h2 className="text-white font-medium">{title}</h2>
          {description && <p className="text-slate-500 text-xs">{description}</p>}
        </div>
      </div>
      <div className="space-y-2">
        {items.map(item => (
          <DocItem key={item.id} item={item} isAdmin={isAdmin} onEdit={onEdit} onDelete={onDelete} />
        ))}
        {items.length === 0 && (
          <p className="text-slate-600 text-sm text-center py-4 border border-dashed border-slate-700 rounded-xl">
            No notes in this section yet.
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Help() {
  const { user } = useAuth()
  const [customNotes, setCustomNotes] = useState([])
  const [editing, setEditing]         = useState(null)   // null | 'new' | noteObj
  const [activeTab, setActiveTab]     = useState('docs') // 'docs' | 'resistant' | 'notes'
  const isAdmin = can(user, 'help.edit')

  useEffect(() => {
    api.get('/help/notes').then(r => setCustomNotes(r.data)).catch(() => {})
  }, [])

  const deleteNote = async id => {
    if (!confirm('Delete this note?')) return
    await api.delete(`/help/notes/${id}`)
    setCustomNotes(n => n.filter(x => x.id !== id))
  }

  const saveNote = note => {
    setCustomNotes(prev => {
      const exists = prev.find(n => n.id === note.id)
      return exists ? prev.map(n => n.id === note.id ? { ...note, _custom: true } : n) : [...prev, { ...note, _custom: true }]
    })
  }

  const customBySection = section => customNotes.filter(n => n.section === section).map(n => ({ ...n, _custom: true }))

  const TABS = [
    { key: 'docs',      label: 'How it works',       icon: BookOpen },
    { key: 'resistant', label: 'Resistant vendors',  icon: ShieldAlert },
    { key: 'general',   label: 'Templates & tips',   icon: Lightbulb },
  ]

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Help & documentation</h1>
          <p className="text-slate-400 text-sm mt-0.5">Guides, templates, and tactics for data removal</p>
        </div>
        {isAdmin && (
          <button onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <Plus size={13} /> Add note
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-800 p-1 rounded-lg border border-slate-700/50 mb-6 w-fit">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
              activeTab === t.key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}>
            <t.icon size={13} />{t.label}
          </button>
        ))}
      </div>

      {/* How it works */}
      {activeTab === 'docs' && (
        <>
          <DocSection
            icon={BookOpen} title="Setup & how it works"
            description="Understanding the removal pipeline"
            items={[...STATIC_DOCS.setup, ...customBySection('setup')]}
            isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
          />
        </>
      )}

      {/* Resistant vendors */}
      {activeTab === 'resistant' && (
        <>
          <div className="flex items-center gap-2 mb-4 px-3 py-2.5 bg-amber-900/20 border border-amber-800 rounded-lg">
            <AlertTriangle size={13} className="text-amber-400 shrink-0" />
            <p className="text-amber-300 text-xs">
              These brokers require extra effort. Standard form submissions are often ignored. Use the specific methods below.
            </p>
          </div>
          <DocSection
            icon={ShieldAlert} title="Resistant & difficult vendors"
            description="Specific tactics for brokers that don't comply with standard opt-outs"
            color="text-red-400"
            items={[...STATIC_DOCS.resistant, ...customBySection('resistant')]}
            isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
          />
        </>
      )}

      {/* General tips */}
      {activeTab === 'general' && (
        <>
          <DocSection
            icon={Lightbulb} title="Templates & general tips"
            description="Reusable templates and strategies for more effective removal"
            color="text-amber-400"
            items={[...STATIC_DOCS.general, ...customBySection('general')]}
            isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
          />
          {customBySection('general').length === 0 && isAdmin && (
            <div className="text-center mt-2">
              <button onClick={() => setEditing('new')} className="text-shield-400 text-sm hover:underline">
                + Add a custom note to this section
              </button>
            </div>
          )}
        </>
      )}

      {(editing === 'new' || (editing && typeof editing === 'object')) && (
        <NoteModal
          initial={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={saveNote}
        />
      )}
    </div>
  )
}
