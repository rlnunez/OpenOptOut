import { useEffect, useState } from 'react'
import {
  BookOpen, Shield, Mail, AlertTriangle, Plus,
  Edit3, Trash2, X, Check, ChevronDown, ChevronRight,
  ExternalLink, Info, Lightbulb, ShieldAlert, Copy
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { isSafeHref } from '../components/Markdown'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'
import { detailText } from '../errorMessage'
import Modal from '../components/Modal'

// ── Static documentation data ─────────────────────────────────────────────────

const STATIC_DOCS = {
  setup: [
    {
      id: 'how-it-works',
      title: tx("How OpenOptOut works"),
      content: tx("Data brokers are companies that collect your name, address, phone number and other details and sell them or post them online. OpenOptOut asks them to take your details down, and keeps checking that they stay down.\n\n**It works in four steps:**\n\n1. **Your details** — For each person in your family, add every name, email, phone number and address they've used, including old ones. The more you add, the more listings we can find.\n\n2. **Find listings** — We search broker sites and the web to see which ones have a page about you.\n\n3. **Ask for removal** — We fill in each site's opt-out form or send it an email asking it to delete your details. Each email goes out from its own address, so we can tell which site wrote back.\n\n4. **Check replies and check again** — We read the replies, click the confirmation links, and mark a listing as removed once the site confirms it. Later we look again, because many sites put people back after a few months. If your page comes back, we ask again.\n\nSome sites need a person to finish: a CAPTCHA, a phone call, or a letter. Those show up on your **Checklist**."),
    },
    {
      id: 'email-setup',
      title: tx("Setting up your removal email"),
      content: tx("We suggest a **separate email address** just for removal requests, apart from your everyday inbox.\n\n**Why a separate address?**\n- Some sites add people who opt out to marketing lists. A separate inbox keeps that mess away from you.\n- Every reply lands in one place, so it's easy to see who answered.\n\n**Easiest way (Gmail, Outlook or Yahoo):**\n1. Make a new Gmail, Outlook or Yahoo address, for example yourname.removals@gmail.com.\n2. Go to **Email inboxes** and choose **Connect an inbox**.\n3. Pick Google, Microsoft or Yahoo and sign in. You never type your password into OpenOptOut, and you can disconnect at any time.\n\n**Other email services (Fastmail and others):**\n1. Turn on two-step sign-in for the account.\n2. In the account's security settings, make an **app password** (a separate password just for apps like this one).\n3. Go to **Email inboxes**, choose **Connect an inbox**, pick your service, and paste the app password, not your normal one.\n\nGmail and Outlook let every opt-out use its own address (like you+oo7f3k2a@gmail.com), which is how we match each reply to the right site."),
    },
    {
      id: 'recheck-explained',
      title: tx("Why we check again"),
      content: tx("Getting removed once doesn't mean you stay removed. Broker sites keep collecting public records and other data, and many put people back within **1 to 3 months**.\n\n**How it works:**\n- When a site confirms it removed you, we set a date to check again (90 days unless you change it).\n- On that date we look at the site. If your page is back, we ask for removal again.\n- We also run a weekly web search to spot your details showing up anywhere new.\n\n**Changing how often we check:**\nGo to **Settings** and change how many days to wait before checking again. Sites that often put people back are worth checking every 30 days.\n\n**The Check again page** lists what's due now and what's coming up. You can send a request again right away, or push a check later if you've already looked yourself."),
    },
    {
      id: 'database-scaling',
      title: tx("Database scaling — SQLite vs PostgreSQL"),
      content: tx("OpenOptOut defaults to SQLite for simplicity, but PostgreSQL is strongly recommended for institutional deployments with more than ~100 concurrent users.\n\n**SQLite is fine for:**\n- Library staff deployments (10–200 users)\n- Personal/family use\n- Testing and evaluation\n- Single-instance deployments without high concurrency\n\n**Switch to PostgreSQL when:**\n- Deploying for library patrons (potentially thousands of users)\n- More than ~500 total user accounts\n- Running the opt-out scheduler on a busy instance\n- Need for connection pooling across multiple app instances\n- High availability or read replicas required\n\n**Harris County example:**\nHarris County Public Library serves 4.7 million residents across 26 branches. A patron-facing deployment could have 50,000+ registered users. At that scale:\n- SQLite would show \"database locked\" errors under concurrent opt-out runs\n- PostgreSQL handles thousands of concurrent connections cleanly\n- Connection pooling (PgBouncer) is recommended above 200 concurrent users\n\n**Migration:**\nGo to Admin → Database → \"Migrate to PostgreSQL\". The tool copies all data table-by-table with full integrity preservation. Run during off-hours and keep the SQLite backup for 30 days.\n\n**Recommended Postgres providers:**\n- **Supabase** (free tier, easy setup) — supabase.com\n- **Railway** ($5/month, one-click Postgres) — railway.app\n- **Neon** (serverless Postgres, generous free tier) — neon.tech\n- **Amazon RDS** (enterprise, with automated backups and encryption)\n- **Self-hosted** on the same Docker host with a postgres container"),
    },
    {
      id: 'postgres-setup',
      title: tx("PostgreSQL setup guide"),
      content: tx("**Option 1 — Add Postgres to your Docker Compose:**\n\nAdd this to your docker-compose.yml:\n\n```yaml\nservices:\n  db:\n    image: postgres:16-alpine\n    environment:\n      POSTGRES_DB: openoptout\n      POSTGRES_USER: ps_user\n      POSTGRES_PASSWORD: your-strong-password\n    volumes:\n      - pg_data:/var/lib/postgresql/data\n    restart: unless-stopped\n\n  api:\n    environment:\n      - DATABASE_URL=postgresql://ps_user:your-strong-password@db:5432/openoptout\n\nvolumes:\n  pg_data:\n```\n\n**Option 2 — Managed Postgres (Supabase example):**\n\n1. Create a project at supabase.com\n2. Go to Settings → Database → Connection string\n3. Copy the URI (starts with postgresql://)\n4. Set DATABASE_URL in your .env file\n5. Restart the container\n\n**Option 3 — Neon (serverless, scales to zero):**\n\n1. Create a project at neon.tech\n2. Copy the connection string from the dashboard\n3. Set DATABASE_URL in your .env file\n\n**After changing DATABASE_URL:**\nIf migrating from SQLite, use the migration tool in Admin → Database first.\nIf starting fresh, just set the URL and restart — the schema is created automatically."),
    },
    {
      id: 'db-enterprise-auth',
      title: tx("Enterprise database authentication"),
      content: tx("For deployments where a plain username/password connection string is not acceptable, OpenOptOut supports several PostgreSQL authentication methods configurable under Admin → Database → Connection.\n\n**Security principle:**\nSecrets (passwords, private keys, certificates) are never stored in the application database or settings. They live in environment variables or mounted files that your database administrator controls. The app only reads them — it never writes, displays, or logs them.\n\n**Supported methods:**\n\n- **Password (SCRAM-SHA-256)** — standard auth. Combine with an SSL mode to encrypt in transit.\n- **Password over verified TLS** — password auth with full certificate verification (sslmode=verify-full).\n- **Client certificate (mutual TLS)** — the strongest common method. The client presents a certificate; no password is transmitted at all. Requires a CA cert, client cert, and client private key mounted as files.\n- **Client certificate + password** — requires both, for high-security environments (finance, healthcare, government).\n- **AWS RDS IAM** — short-lived (15-minute) tokens instead of a static password. Requires an IAM role and boto3.\n- **GCP Cloud SQL IAM** — OAuth2 tokens from a service account. Requires google-auth.\n- **Azure AD** — access tokens via managed identity. Requires azure-identity.\n- **Kerberos / GSSAPI** — enterprise single sign-on using the ticket cache. Common in Active Directory environments.\n\n**Where secrets go:**\n\n| Material | Location |\n|---|---|\n| Password | DB_PASSWORD env var, or DB_PASSWORD_FILE (Docker/K8s secret) |\n| CA certificate | Mounted file, path set in the UI |\n| Client cert | Mounted file, path set in the UI |\n| Client private key | Mounted file, chmod 600, owned by app user |\n| Cloud IAM | IAM role / service account / managed identity (no static secret) |\n\n**Mounting certificates in Docker Compose:**\n\nAdd to the api service:\n```yaml\nvolumes:\n  - /host/certs/ca.pem:/certs/ca.pem:ro\n  - /host/certs/client-cert.pem:/certs/client-cert.pem:ro\n  - /host/certs/client-key.pem:/certs/client-key.pem:ro\nsecrets:\n  - db_password\n```\n\nThen set the file paths in the Connection config UI, and set DB_PASSWORD_FILE=/run/secrets/db_password.\n\n**Cloud IAM dependencies** are optional — install only what you need:\n```\npip install -r requirements-cloud.txt\n```\n\nClient-certificate auth with sslmode=verify-full is recommended for the highest security — no password is ever transmitted or stored, and both the client and server verify each other's identity."),
    },
    {
      id: 'bot-evasion',
      title: tx("Avoiding broker blocking"),
      content: tx("Data brokers increasingly detect and block automated form submissions. OpenOptOut includes several measures to reduce blocking, configurable under Settings → Automation.\n\n**User-agent rotation:**\nEach broker submission uses a randomized browser fingerprint from a pool of ~15 current, real user agents (Chrome, Firefox, Safari, Edge across Windows and macOS). The viewport is matched to the platform so the browser context is internally consistent. Admins can add custom user-agent strings to expand the pool.\n\n**Honest limitations:**\nUser-agent rotation is one layer, not a complete solution. Sophisticated brokers also fingerprint:\n- TLS handshake signatures\n- Canvas and WebGL rendering\n- Request timing patterns\n- Mouse movement and interaction\n\nRotation is most effective against simple UA-based blocking. It meaningfully raises the bar but does not defeat advanced bot-detection systems like those from Cloudflare or PerimeterX.\n\n**Submission timing:**\nThe delay between submissions (default 1.5 seconds) makes traffic look less automated. Increasing it to 3–5 seconds reduces the chance of rate-limit blocks at the cost of slower throughput.\n\n**Spreading out jobs:**\nRather than sending all opt-outs in one nightly burst — which creates an obvious traffic spike — you can spread them out (Settings → Scheduler):\n\n- **Burst** — all at once at the run time (simplest, most detectable)\n- **Time window** — spread evenly across a window like 10pm–6am\n- **Rate limited** — a fixed number per hour, continuously\n- **Distributed** — small batches spread across 24 hours (least detectable)\n\nFor a large deployment (e.g. a library serving thousands of patrons), distributed or rate-limited mode is strongly recommended. A nightly burst of thousands of submissions from one IP is both easy to detect and likely to overwhelm the container.\n\n**Daily caps per person (spreads a new signup over days):**\nA new member can have hundreds of pending opt-outs. Rather than firing all of them at once — a screaming automation signal — the scheduler caps how many brokers are submitted per member per day (Settings → Scheduler → *max opt-outs per day*, default 20), with a global system ceiling on top, whichever is reached first. A single member's pending brokers then clear gradually over weeks, which both looks far more human and protects your shared proxy pool. Individual members can be given a higher or lower cap for special cases (Scheduled → per-member config). Within each day's budget, brokers are dispatched **highest-priority-first** (a 1–5 priority per broker, 5 = highest). New brokers get a sensible auto-priority (property/resistant brokers rank highest), and a super admin can override it — per broker, in bulk, or with rules (\"all property brokers = 5\") — on the **Broker priority** admin page, and share those priorities between deployments via export/import. So a person's most sensitive exposures clear earliest.\n\n**IP masking (the most effective measure):**\nBrokers track and block primarily by IP address. A datacenter IP (what your server likely has) is the biggest tell. Configure proxies under Settings → Proxy:\n\n- **Single proxy** — all traffic exits one IP\n- **Rotating pool** — a different IP per broker, the strongest configuration\n\nResidential proxies (real home ISP IPs) work far better than datacenter proxies or VPNs, which brokers block easily. Reputable providers include Bright Data, Oxylabs, Smartproxy/Decodo, and IPRoyal — the app has presets for each. Proxy credentials are read only from environment variables or mounted files, never stored in the app.\n\nUse the \"Test proxy\" button to confirm your traffic is actually exiting through the proxy IP before running a batch.\n\n**Recommended stack for a large deployment:**\nRotating residential proxy pool + user-agent rotation + distributed job spreading + 3–5 second submission delays. This combination looks very much like ordinary human traffic. Prioritize email-based opt-outs over form submissions for the most aggressive brokers."),
    },
    {
      id: 'proxy-vpn-providers',
      title: tx("Proxy & VPN provider recommendations"),
      content: tx("There are two distinct needs here, and they call for different tools. **Proxies** mask the IP of the automation engine so brokers don't block your opt-out submissions. **VPNs** protect the privacy of an individual person's everyday browsing. Don't confuse the two — a consumer VPN is a poor fit for the automation engine, and a datacenter proxy does nothing for personal privacy.\n\nThese are informational recommendations to help you evaluate options, not endorsements. Pricing, ownership, and policies change — verify current details and read the provider's own terms before committing. Neither OpenOptOut nor its maintainers are affiliated with any provider below.\n\n*Last reviewed: July 2026. Provider pricing, ownership, and policies change frequently — re-verify before relying on any detail here.*\n\n---\n\n**PART 1 — Residential proxy providers (for the automation engine)**\n\nFor submitting opt-outs at scale, residential proxies are the effective choice. They route through real home-ISP IP addresses, so submissions look like an ordinary person. The app has built-in presets for the first four.\n\nThe single most important thing to check is **how the provider sources its IPs.** Ethical providers get explicit, informed consent from the people whose connections form the network (usually by paying them or bundling it into an app with a clear opt-in). Unethical ones acquire IPs through malware or hidden SDKs. Since you're routing opt-out traffic through these IPs, sourcing integrity is both an ethical and a reputational matter for your institution.\n\n- **Bright Data** — the largest residential network, with detailed compliance documentation and a published KYC process for customers. Enterprise-oriented, with granular geo-targeting. Higher price point; extensive controls. Has an app preset.\n- **Oxylabs** — enterprise-grade, strong compliance posture, good support and documentation. Similar tier to Bright Data. Has an app preset.\n- **Smartproxy / Decodo** — mid-market, more approachable pricing and a simpler dashboard. A common starting point for smaller deployments. Has an app preset.\n- **IPRoyal** — budget-friendly, pay-as-you-go options, sources IPs through its \"Pawns\" app where users are paid and opt in. Has an app preset.\n- **SOAX** — clean-IP focus with granular geo and consent-based sourcing. Well regarded; configure via the generic preset.\n\n**Practical notes for proxies:**\n- Match the proxy's geography to the residents you serve — U.S. brokers respond best to U.S. residential IPs, and some behave differently by region.\n- Choose *rotating* residential endpoints for pool mode, or *sticky sessions* if a broker's flow needs the same IP across several page loads.\n- Residential proxies are billed by bandwidth, not by request. Opt-out forms are light, so usage is typically modest, but monitor it on the provider dashboard.\n- Always use the \"Test proxy\" button first to confirm your exit IP, then run a small batch before scaling up.\n\n**What to avoid for the automation engine:** free proxy lists (often malware-sourced or logging your traffic), most datacenter proxies (brokers block these ranges wholesale), and consumer VPNs (shared exit IPs that are widely flagged).\n\n---\n\n**PART 2 — VPN providers (for individual privacy)**\n\nA VPN is the right tool for a *person* who wants to reduce tracking of their own browsing, hide their IP from the sites they visit, and encrypt traffic on untrusted networks (library Wi-Fi, hotels, airports). It is not what the automation engine uses, but patrons and staff often ask what to use personally, so it's worth having recommendations on hand.\n\nWhen evaluating a VPN, the things that actually matter for privacy are: an **independently audited no-logs policy**, ownership and jurisdiction you're comfortable with, modern protocols (WireGuard/OpenVPN), and a sustainable business model — if it's free, your data is usually the product.\n\n- **Mullvad** — widely regarded as a privacy gold standard. Flat €5/month, accepts cash and anonymous account numbers (no email required), no personal info collected, independently audited. Based in Sweden.\n- **Proton VPN** — from the makers of Proton Mail, audited no-logs policy, strong transparency, and a genuinely usable free tier (rare among trustworthy providers). Based in Switzerland; open-source apps.\n- **IVPN** — privacy-first, audited, minimal data collection, anonymous account IDs. Transparent ownership. A strong Mullvad alternative.\n- **Windscribe** — flexible, with a capable free tier; good for lighter needs. Read their logging policy to confirm it fits your threshold.\n\n**Free-tier caveat:** Proton VPN and Windscribe offer legitimate free tiers. Be cautious with *other* free VPNs — many monetize by logging and selling browsing data, which is the opposite of what someone seeking privacy wants. \"Free\" and \"private\" rarely coexist unless a trustworthy paid product is subsidizing the free tier.\n\n**For a library context:** Mullvad and Proton VPN are the easiest to recommend to patrons — Mullvad for its no-account-required model, Proton for its usable free tier and name recognition. Both let a person try the service without handing over personal information, which is itself a privacy win.\n\n---\n\n**One-line summary:** use *residential proxies* (Bright Data, Oxylabs, Smartproxy/Decodo, IPRoyal, SOAX) for the opt-out automation, and recommend *audited no-logs VPNs* (Mullvad, Proton VPN, IVPN) to individuals for their personal browsing privacy."),
    },
  ],

  protect: [
    {
      id: 'phone-private',
      title: tx("Make your phone number private"),
      content: tx("Your phone number is one of the main ways data brokers link records together. OpenOptOut handles the sites. Your phone company handles the rest, and only you can change those settings.\n\n**What OpenOptOut does for you:**\n- Searches the web for each saved number.\n- Sends removal requests to caller ID apps (Truecaller, Hiya, Sync.ME, CallApp) and reverse phone lookup sites (Spy Dialer, NumLookup, CallerSmart, ReversePhoneLookup, NumberGuru). Each saved number gets its own request, because these sites list people by number.\n- Checks again later, one search per number, and asks again if a number shows up.\n\n**What to do with your phone company (10 minutes, once):**\n1. **Change or remove the caller ID name.** This is the name people see when you call. Set it to your initials or first name only. See the guide for your carrier below.\n2. **Turn off advertising and data-sharing programs.** Most carriers turn these on by default.\n3. **Limit \"CPNI\" use.** CPNI is the record of who you call, when, and what plan you have. You can tell the carrier not to use it for marketing.\n4. **Turn on number lock / a port-out PIN.** This stops someone from moving your number to another phone (a SIM swap). It's not about privacy, but you'll be on the same settings page.\n5. **Register on the Do Not Call list** at donotcall.gov. It doesn't remove listings, but it cuts sales calls.\n\n**Hide your number on a single call:** dial *67 before the number (US). Calls to 911 and to toll-free numbers still show your number.\n\n**Hide your number on every call:** iPhone: Settings → Apps → Phone → Show My Caller ID. Android: Phone app → Settings → Calls (or Supplementary services) → Caller ID. If the switch is greyed out, ask your carrier for \"per-line caller ID blocking\".\n\n**Old landline?** Ask the phone company to make the number \"non-published\" so it stays out of directories. There may be a monthly fee."),
    },
    {
      id: 'carrier-verizon',
      title: tx("Verizon, Visible, Total Wireless, Straight Talk and other Verizon brands"),
      content: tx("Verizon's privacy policy also covers its prepaid brands: **Visible, Total Wireless, Straight Talk, Tracfone, Simple Mobile, Walmart Family Mobile, Net10, Go Smart, Page Plus and SafeLink.**\n\n**Verizon (monthly plans):**\n1. Open **verizonwireless.com/myprivacy**, or in the My Verizon app go to **Edit profile & settings → Privacy preferences**.\n2. Set **Custom Experience** to \"Don't use\".\n3. Check **Custom Experience Plus** is off.\n4. Set **Business and Marketing Insights** to \"Don't use\". The account owner can change all lines at once.\n5. On the **CPNI** tab, choose \"don't share\" for each line, or call 1-800-333-9956.\n6. Prefer the phone? Call 1-866-211-0874 for the advertising and insights programs.\n\n**Caller ID name (Verizon):** My Verizon → Account → My Devices (or Manage Device in the app) → choose the line → **Caller ID** or **Share Name ID** → change the name and save. It can take up to 24 hours to update everywhere.\n\n**Visible, Total Wireless, Straight Talk and the other prepaid brands:** look for **\"Your Privacy Choices\"** at the bottom of the brand's own website and turn off sale and sharing. The same page lets you opt out of Verizon's identity-verification sharing.\n\n**Fios or Frontier internet at home:** My Verizon → Account → Home → Services → Internet → **Manage online advertising preferences** → \"Do Not Participate\"."),
    },
    {
      id: 'carrier-att',
      title: tx("AT&T and Cricket"),
      content: tx("**AT&T:**\n1. Sign in at att.com, click your profile icon, then **Privacy Choices**. In the app: More → Manage Profile → Privacy Choices.\n2. Turn off **\"Allow AT&T to share or sell my personal information\"**, **Personalized Plus**, **Personalized** and **DNS Error Assist**, then save.\n3. Have AT&T internet or TV too? Repeat for each account.\n4. **CPNI:** use AT&T's CPNI restriction form (you'll need the billing account number and billing ZIP) and tick \"Restrict use of my CPNI\".\n5. Prefer the phone? Call 866-385-3193 to opt out of sale and sharing.\n\n**Caller ID name (AT&T):** sign in → profile → Settings → expand the line → edit **Caller ID** → save. It can take up to 72 hours. Prepaid lines always show \"Wireless Caller\".\n\n**Cricket Wireless** (owned by AT&T):\n- Sale, sharing and the \"Personalized Program\": cricketwireless.com/cmp/ccpa/dnscricket\n- CPNI: cricketwireless.com/legal-info/customer-choices-and-controls-CPNI.html\n- Questions about a request: 1-844-246-1628"),
    },
    {
      id: 'carrier-tmobile',
      title: tx("T-Mobile, Metro, Mint, Ultra and US Cellular"),
      content: tx("**T-Mobile and Metro by T-Mobile:**\n1. Open the **Privacy Dashboard** at t-mobile.com/privacy-center/dashboard. In the T-Life app: Manage → gear icon → Privacy and policies → Privacy Dashboard.\n2. Turn off **Relevant Ads**, **Analytics and Reporting**, **Profiling** and sale/sharing.\n3. Check **Tailored Offers and Ads** and the old **Personalized Ads and Offers** are off. Both use CPNI only if you agreed, so leaving them off keeps CPNI out of marketing.\n4. Prefer the phone? T-Mobile 1-800-937-8997, Metro 1-888-863-8768, or dial 611.\n\n**Caller ID name (T-Mobile):** T-Life app → Manage → Device Settings → enter a new caller ID name. To keep your name out of caller ID entirely, call customer care.\n\n**Mint Mobile:** click **\"Do Not Sell or Share My Personal Information\"** at the bottom of mintmobile.com. A browser with Global Privacy Control turned on (Firefox, Brave, DuckDuckGo) opts you out automatically. Mint says it doesn't use CPNI in ways that need your permission.\n\n**Ultra Mobile and US Cellular** are now part of T-Mobile. Look for the \"Your Privacy Choices\" link on the brand's site, or use the T-Mobile Privacy Dashboard once your account has moved to T-Mobile."),
    },
    {
      id: 'carrier-others',
      title: tx("Google Fi, Xfinity, Spectrum, Boost and other carriers"),
      content: tx("Many smaller carriers rent space on a big carrier's network, but **your account, and your privacy settings, are with the company you pay.** Change them there.\n\n**Google Fi:** fi.google.com → Settings → Privacy & security → untick **\"Allow CPNI sharing\"** (or go to fi.google.com/cpni-opt-out). This isn't in the Fi app, so use a web browser.\n\n**Xfinity Mobile:** sign in at **xfinity.com/privacy/opt-out** to turn everything off in one click, and limit sensitive data at xfinity.com/privacy/requests/choice. Turn on **Number Lock** while you're there.\n\n**Spectrum Mobile:** spectrum.com/policies/your-privacy-rights-opt-out (\"Do Not Sell or Share / Opt-Out of Targeted Advertising\").\n\n**Boost Mobile:** boostmobile.com/yourprivacychoices, or call 833-502-6678.\n\n**Everyone else** (Consumer Cellular, US Mobile, Tello, Red Pocket, Ting, H2O, Lycamobile, Cox Mobile, Helium and others):\n1. Scroll to the bottom of the carrier's website and click **\"Your Privacy Choices\"** or **\"Do Not Sell or Share My Personal Information\"**. Turn everything off.\n2. Turn on **Global Privacy Control** in your browser (built into Firefox, Brave and DuckDuckGo). Many carriers treat it as an opt-out.\n3. Call or chat with customer care and ask them to: **restrict CPNI use for marketing**, **remove or change the caller ID name** on your line, and **add a port-out PIN or number lock**.\n4. Prepaid lines often show only \"Wireless Caller\" or the city. In that case the name people see comes from caller ID apps, which OpenOptOut handles.\n\n**Which network is my carrier on?** It doesn't change what you need to do, but for reference: Visible, Total, Straight Talk and Cox Mobile use Verizon; Cricket uses AT&T; Metro, Mint, Ultra, Google Fi and Tello use T-Mobile; Xfinity and Spectrum use Verizon plus Wi-Fi; Boost has its own network plus AT&T; US Mobile and Consumer Cellular offer more than one."),
    },
    {
      id: 'credit-freeze',
      title: tx("Freeze your credit"),
      content: tx("A credit freeze stops anyone opening new credit in your name. It's **free**, doesn't affect your score, and you can lift it for a day when you need a loan. It's the strongest protection against identity theft, and it works even if your details are already out there.\n\n**Fastest: do it online or by phone (about 10 minutes each):**\n- **Equifax:** equifax.com/personal/credit-report-services/credit-freeze/ · 888-298-0045\n- **Experian:** experian.com/help/credit-freeze/ · 888-397-3742\n- **TransUnion:** transunion.com/credit-freeze · 888-909-8872\n\nOnline and phone freezes usually take effect right away. Freeze all three: lenders pick one.\n\n**Prefer mail?** Open **Freeze credit** in the menu. It prints a ready letter for each bureau with your name, address and birthday filled in, the mailing address, and the list of copies to enclose. Mailed freezes take about 3 business days after they arrive.\n\n**OpenOptOut never stores Social Security numbers.** The letters leave a blank to write it in by hand.\n\n**Smaller agencies worth freezing too:** Innovis, NCTUE (phone and utility accounts), ChexSystems (bank accounts) and LexisNexis Risk Solutions (insurance and identity checks). Each has a free freeze. The Freeze credit page lists them.\n\n**Already a victim?** Report it at identitytheft.gov and place a fraud alert. One bureau tells the other two, and an extended alert lasts seven years."),
    },
    {
      id: 'child-freeze',
      title: tx("Freeze your child's credit"),
      content: tx("Children's Social Security numbers are a favourite target: nobody checks a child's credit, so theft can go unnoticed for years. Since 2018, US law lets a parent or guardian freeze the credit of a child **under 16** for free, even if the child has no credit file yet. The bureau creates a file just to freeze it.\n\n**How:** by mail, to each of the three bureaus. Experian also takes requests online at experian.com/help/minor-request/. Open **Freeze credit**, choose your child and \"Child under 16\", pick yourself as the parent, and print the three letters.\n\n**Put copies (never originals) of these in each envelope:**\n- The child's birth certificate\n- The child's Social Security card\n- Your government photo ID\n- A utility bill or bank statement showing your name and address\n- If your name isn't on the birth certificate: the court order, guardianship papers or power of attorney\n\n**Where to send them:**\n- **Equifax:** Equifax Information Services LLC, P.O. Box 105788, Atlanta, GA 30348-5788. Include Equifax's Minor Freeze Request form.\n- **Experian:** Experian, P.O. Box 9554, Allen, TX 75013\n- **TransUnion:** TransUnion, P.O. Box 380, Woodlyn, PA 19094. Ask for a \"Protected Consumer Freeze\".\n\nEach bureau mails a confirmation. **Keep it with the child's papers.** When your child turns 16 they can keep it, lift it, or freeze it themselves (16 and 17 year olds can call the bureaus). Lift it before they apply for a first card, loan or student account."),
    },
  ],
  resistant: [
    {
      id: 'epsilon-guide',
      title: tx("Epsilon — email opt-out (resistant)"),
      content: tx("Epsilon is one of the largest upstream data brokers, supplying data to hundreds of smaller sites. Removing from Epsilon can cause your information to disappear from many downstream sites automatically.\n\n**Required: email opt-out (not a web form)**\n\nSend to **all three** of these addresses in the same email:\n- `optout@epsilon.com`\n- `abacusoptout@epsilon.com`\n- `dataoptout1@epsilon.com`\n\n**Subject line:** `Data Removal Request — [Your Full Name]`\n\n**Body should include:**\n- Full name (and any variants/maiden names)\n- Current mailing address\n- Any previous addresses from the last 5 years\n- Statement: *\"Please remove all personal data associated with me from your databases and do not sell or share my information with any third parties.\"*\n\n**Timeline:** 4–6 weeks. Follow up if no response after 30 days. If you're in California, add: *\"I am exercising my rights under the California Consumer Privacy Act (CCPA), Cal. Civ. Code § 1798.105.\"*\n\n**Note:** Epsilon owns multiple brands. One email covers Epsilon Data Management, Abacus, FloSports data, and several others."),
    },
    {
      id: 'ekata-guide',
      title: tx("Ekata (TransUnion) — resistant"),
      content: tx("Ekata is a business-focused identity verification service, now owned by TransUnion. They primarily serve other businesses rather than consumers, which makes consumer opt-outs slow and inconsistent.\n\n**Steps:**\n1. Email `privacy@ekata.com` with subject: `Personal Data Removal Request`\n2. Include your full name, address, and phone number\n3. Reference the CCPA (if applicable): *\"Pursuant to CCPA Cal. Civ. Code § 1798.105, I request deletion of all personal data you hold about me.\"*\n4. CC `privacyrequests@transunion.com` as Ekata is now a TransUnion entity\n\n**Expected timeline:** 6–8 weeks. Ekata is required to respond within 45 days under CCPA.\n\n**If no response:** File a complaint with the California Attorney General's office at oag.ca.gov/privacy/ccpa if you're a California resident. This often prompts action."),
    },
    {
      id: 'sheerid-guide',
      title: tx("SheerID — resistant"),
      content: tx("SheerID is a verification platform used by businesses to verify military, student, and other status. They hold personal data but are resistant to consumer removal requests because their customers (not consumers) are their primary relationship.\n\n**Steps:**\n1. Go to `sheerid.com/privacy-policy` and scroll to \"Your Privacy Rights\"\n2. Submit a deletion request via their online form\n3. Also email `privacy@sheerid.com` with the same request\n4. Include: full name, email addresses, any SheerID-verified programs you've used\n\n**Important:** SheerID data often enters their system through their business customers (e.g. a retailer you bought from). You may also need to contact those retailers separately.\n\n**If they don't respond:** SheerID is subject to GDPR if you're an EU resident and CCPA if you're a California resident. Cite the relevant regulation and request a response within the legally required timeframe."),
    },
    {
      id: 'contactout-guide',
      title: tx("ContactOut — resistant"),
      content: tx("ContactOut aggregates professional contact information (work emails, LinkedIn profiles, phone numbers) and sells access to recruiters. They are particularly resistant because their paying customers depend on this data.\n\n**Steps:**\n1. Visit `contactout.com/optout` — search for yourself and submit removal\n2. Also email `support@contactout.com` referencing your submission\n3. If you have a LinkedIn profile, making it private reduces ContactOut's ability to re-scrape you\n\n**Important:** ContactOut re-scrapes LinkedIn regularly. Even after removal, a public LinkedIn profile may cause re-listing within weeks. Consider making your LinkedIn contact information private or using LinkedIn's own data control settings.\n\n**GDPR note:** ContactOut is based in San Francisco but serves EU clients. EU residents can invoke GDPR Article 17 (right to erasure) for stronger legal footing."),
    },
    {
      id: 'peopleconnect-guide',
      title: tx("PeopleConnect network — one opt-out for many"),
      content: tx("PeopleConnect owns a large network of background check and people-search sites. A single suppression request at their central portal covers all of them.\n\n**Sites covered by one opt-out:**\nIntelius, TruthFinder, Instant Checkmate, US Search, Classmates.com, ZabaSearch, AnyWho, Addresses.com, PublicRecords.com, PeopleLookup, DateCheck, Spock, and more.\n\n**How to opt out:**\n1. Go to `suppression.peopleconnect.us/login`\n2. Create an account (use your dedicated removals email)\n3. Submit a suppression request for each family member separately\n4. You will need to verify via email for each request\n\n**Timeline:** 72 hours to 2 weeks depending on the site.\n\n**Important:** You need to submit a separate request for each name variant and each historical address that appears in their systems. Run a search first to find all your listings."),
    },
    {
      id: 'mylife-guide',
      title: tx("MyLife — difficult, requires phone call"),
      content: tx("MyLife is one of the most difficult brokers to remove from. They have a history of deceptive practices (including an FTC action) and often require multiple attempts.\n\n**Method 1 — Phone (most reliable):**\nCall **(888) 704-1900**, press 2. Ask to be removed from MyLife and Wink.com. Have ready:\n- Your full name and any aliases\n- Date of birth\n- Current and one previous mailing address\n- Email address on their site\n\n**Method 2 — Email:**\nEmail `privacy@mylife.com` and `removalrequests@mylife.com` with your listing URL(s).\n\n**Do not** create an account or pay for a report — this gives them more data and complicates removal.\n\n**Timeline:** 7–14 days. Check back after 2 weeks and repeat if still listed.\n\n**Persistence pays:** MyLife is known to re-list people. Add it to your 30-day re-check list rather than 90-day."),
    },
  ],
  general: [
    {
      id: 'ccpa-template',
      title: tx("CCPA deletion request template"),
      content: tx("If you are a California resident, the California Consumer Privacy Act (CCPA) gives you the right to request deletion of your personal data from any business that collects it.\n\n**Use this template for resistant vendors:**\n\n---\n\nSubject: CCPA Data Deletion Request — [Your Full Name]\n\nTo Whom It May Concern,\n\nI am a California resident exercising my rights under the California Consumer Privacy Act (Cal. Civ. Code § 1798.105) to request the deletion of all personal information you have collected about me.\n\nPlease delete the following data associated with my identity:\n- Full name: [Your Name]\n- Address: [Your Address]\n- Email: [Your Email]\n- Phone: [Your Phone]\n\nI request confirmation of deletion within 45 days as required by law. If you require additional verification of my identity, please contact me at the email address above.\n\n[Your Name]\n[Date]\n\n---\n\n**For EU residents:** Replace the CCPA citation with: *\"I am exercising my rights under GDPR Article 17 (Right to Erasure). Please confirm deletion within 30 days.\"*"),
    },
    {
      id: 'upstream-strategy',
      title: tx("The upstream strategy — remove from the source"),
      content: tx("Many smaller data broker sites don't collect data themselves — they purchase it from a handful of large upstream suppliers. If you remove yourself from the sources, you can trigger automatic removal from dozens of downstream sites.\n\n**The key upstream brokers to prioritize:**\n\n1. **Acxiom** (`isapps.acxiom.com/optout/optout.aspx`) — one of the largest. Data from Acxiom flows to hundreds of sites.\n\n2. **Epsilon** — see the Epsilon guide. Covers many marketing databases.\n\n3. **Data Axle** (formerly InfoUSA/Infogroup) — email `privacy@data-axle.com`\n\n4. **LexisNexis** (`consumer.risk.lexisnexis.com/request`) — major supplier to background check services.\n\n5. **Equifax, Experian, TransUnion** (marketing files, not credit files) — opt out at `optoutprescreen.com` to stop pre-screened credit offers, plus each bureau's own marketing opt-out.\n\n**Timing:** Remove from upstream sources first, then wait 2–3 weeks before submitting downstream requests. Many downstream sites auto-refresh their data — if the source is clean, they may clear automatically."),
    },
  ],
}

// ── Markdown renderer (safe React elements, no dangerouslySetInnerHTML) ──────

function renderInline(text) {
  if (!text) return null
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g
  const parts = text.split(regex)
  return parts.map((part, idx) => {
    if (!part) return null
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      return (
        <code key={idx} className="bg-slate-700 px-1 py-0.5 rounded-sm text-xs text-slate-200 font-mono">
          {part.slice(1, -1)}
        </code>
      )
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
      return (
        <strong key={idx} className="text-white font-medium">
          {part.slice(2, -2)}
        </strong>
      )
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch) {
      const [, label, url] = linkMatch
      if (isSafeHref(url)) {
        return (
          <a key={idx} href={url} target="_blank" rel="noopener noreferrer" className="text-shield-400 underline hover:no-underline">
            {label}
          </a>
        )
      }
      return <span key={idx}>{label}</span>
    }
    return <span key={idx}>{part}</span>
  })
}

function SimpleMarkdown({ content }) {
  const lines = (content || '').split('\n')
  return (
    <div className="space-y-2 text-slate-300 text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />

        // headings
        if (line.startsWith('**') && line.endsWith('**') && !line.slice(2, -2).includes('**'))
          return <p key={i} className="text-white font-medium mt-3">{line.slice(2, -2)}</p>

        // horizontal rule
        if (line.trim() === '---')
          return <hr key={i} className="border-slate-700 my-3" />

        // bullet points
        if (line.startsWith('- ') || line.startsWith('* '))
          return (
            <div key={i} className="flex gap-2 ms-2">
              <span className="text-slate-600 mt-1 shrink-0">•</span>
              <span className="flex-1">{renderInline(line.slice(2))}</span>
            </div>
          )

        // numbered list
        if (/^\d+\.\s/.test(line)) {
          const [num, ...rest] = line.split('. ')
          return (
            <div key={i} className="flex gap-2 ms-2">
              <span className="text-slate-500 shrink-0 font-mono text-xs mt-0.5">{num}.</span>
              <span className="flex-1">{renderInline(rest.join('. '))}</span>
            </div>
          )
        }

        return <p key={i}>{renderInline(line)}</p>
      })}
    </div>
  )
}

// ── Accordion item ────────────────────────────────────────────────────────────

function DocItem({ item, isAdmin, onEdit, onDelete }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-slate-700/50 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/50 transition-colors text-start">
        <span className="text-slate-200 text-sm font-medium">{item.title}</span>
        <div className="flex items-center gap-2">
          {isAdmin && item._custom && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
              <button onClick={e => { e.stopPropagation(); onEdit(item) }}
                aria-label={tx("Edit")}
                className="p-1 text-slate-500 hover:text-shield-400 transition-colors"><Edit3 size={12} /></button>
              <button onClick={e => { e.stopPropagation(); onDelete(item.id) }}
                aria-label={tx("Delete")}
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
              {tx("Last updated by {updated_by} · {v}", { updated_by: item.updated_by, v: fmtDate(item.updated_at) })}
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
    if (!form.title.trim() || !form.content.trim()) { setError(tx("Title and content are required")); return }
    setSaving(true); setError('')
    try {
      const { data } = initial
        ? await api.patch(`/help/notes/${initial.id}`, form)
        : await api.post('/help/notes', form)
      onSaved(data); onClose()
    } catch (e) {
      setError(detailText(e) ?? tx("Save failed"))
    } finally { setSaving(false) }
  }

  return (
    <Modal
      title={initial ? tx("Edit note") : tx("Add custom note")}
      onClose={onClose}
      maxWidth="max-w-2xl"
      className="flex flex-col"
    >
      {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
      <div className="space-y-3 flex-1 overflow-y-auto">
        <div>
          <label className="text-slate-400 text-xs mb-1 block">{tx("Title")}</label>
          <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
            placeholder={tx("e.g. How to opt out of Acxiom")} autoFocus
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500" />
        </div>
        <div>
          <label className="text-slate-400 text-xs mb-1 block">{tx("Section")}</label>
          <select value={form.section} onChange={e => setForm(f => ({...f, section: e.target.value}))}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-hidden">
            <option value="general">{tx("General")}</option>
            <option value="protect">{tx("Phone & credit")}</option>
            <option value="resistant">{tx("Resistant vendors")}</option>
            <option value="setup">{tx("Setup & configuration")}</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="text-slate-400 text-xs mb-1 block">{tx("Content (Markdown supported)")}</label>
          <textarea value={form.content} onChange={e => setForm(f => ({...f, content: e.target.value}))}
            rows={12} placeholder={tx("Write your documentation here. **Bold**, `code`, [links](url), and bullet lists are supported.")}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500 font-mono resize-none" />
        </div>
      </div>
      <div className="flex gap-2 pt-4">
        <button onClick={onClose} className="flex-1 py-2 border border-slate-700 rounded-lg text-slate-400 text-sm hover:bg-slate-800 transition-colors">{tx("Cancel")}</button>
        <button onClick={save} disabled={saving}
          className="flex-1 py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
          {saving ? tx("Saving…") : initial ? tx("Save changes") : tx("Add note")}
        </button>
      </div>
    </Modal>
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
            {tx("No notes in this section yet.")}
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
  const [versionInfo, setVersionInfo] = useState(null)
  const [copiedReport, setCopiedReport] = useState(false)
  const isAdmin = can(user, 'help.edit')

  useEffect(() => {
    api.get('/help/notes').then(r => setCustomNotes(r.data)).catch(() => {})
    api.get('/health').then(r => setVersionInfo(r.data)).catch(() => {})
  }, [])

  const deleteNote = async id => {
    if (!confirm(tx("Delete this note?"))) return
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
    { key: 'docs',      label: tx("How it works"),          icon: BookOpen },
    { key: 'protect',   label: tx("Phone & credit"),        icon: Shield },
    { key: 'resistant', label: tx("Resistant vendors"),     icon: ShieldAlert },
    { key: 'general',   label: tx("Templates & tips"),      icon: Lightbulb },
    { key: 'system',    label: tx("System & Issue Report"), icon: Info },
  ]

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-white text-xl font-semibold">{tx("Help & documentation")}</h1>
            {versionInfo?.version && (
              <span className="text-xs font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700/60">
                {tx("v{version}", { version: versionInfo.version })}
              </span>
            )}
          </div>
          <p className="text-slate-400 text-sm mt-0.5">{tx("Guides, templates, and tactics for data removal")}</p>
        </div>
        {isAdmin && (
          <button onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <Plus size={13} />{" "}{tx("Add note")}
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
            icon={BookOpen} title={tx("Setup & how it works")}
            description={tx("Understanding the removal pipeline")}
            items={[...STATIC_DOCS.setup, ...customBySection('setup')]}
            isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
          />
        </>
      )}

      {/* Phone & credit */}
      {activeTab === 'protect' && (
        <DocSection
          icon={Shield} title={tx("Phone number and credit protection")}
          description={tx("Settings only you can change with your phone company and the credit bureaus")}
          items={[...STATIC_DOCS.protect, ...customBySection('protect')]}
          isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
        />
      )}

      {/* Resistant vendors */}
      {activeTab === 'resistant' && (
        <>
          <div className="flex items-center gap-2 mb-4 px-3 py-2.5 bg-amber-900/20 border border-amber-800 rounded-lg">
            <AlertTriangle size={13} className="text-amber-400 shrink-0" />
            <p className="text-amber-300 text-xs">
              {tx("These brokers require extra effort. Standard form submissions are often ignored. Use the specific methods below.")}
            </p>
          </div>
          <DocSection
            icon={ShieldAlert} title={tx("Resistant & difficult vendors")}
            description={tx("Specific tactics for brokers that don't comply with standard opt-outs")}
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
            icon={Lightbulb} title={tx("Templates & general tips")}
            description={tx("Reusable templates and strategies for more effective removal")}
            color="text-amber-400"
            items={[...STATIC_DOCS.general, ...customBySection('general')]}
            isAdmin={isAdmin} onEdit={setEditing} onDelete={deleteNote}
          />
          {customBySection('general').length === 0 && isAdmin && (
            <div className="text-center mt-2">
              <button onClick={() => setEditing('new')} className="text-shield-400 text-sm hover:underline">
                {tx("+ Add a custom note to this section")}
              </button>
            </div>
          )}
        </>
      )}

      {/* System info & Issue report */}
      {activeTab === 'system' && (
        <div className="space-y-6">
          <div className="bg-slate-800/80 rounded-xl border border-slate-700/60 p-5">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div className="flex items-start gap-3">
                <Info size={18} className="text-shield-400 mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-white font-medium text-base">{tx("System Details & Issue Reporting")}</h2>
                  <p className="text-slate-400 text-xs mt-0.5">
                    {tx("When submitting bug reports, feature requests, or seeking technical support, include the system details below.")}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  const report = [
                    '### OpenOptOut System Report',
                    `- **App Version**: ${versionInfo?.version || 'unknown'}`,
                    `- **Git Commit**: ${versionInfo?.commit || 'unknown'}`,
                    `- **API Status**: ${versionInfo?.status || 'ok'}`,
                    `- **Account Role**: ${user?.role || 'unknown'}`,
                    `- **Platform/Browser**: ${typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown'}`,
                    `- **Reported At**: ${new Date().toISOString()}`,
                  ].join('\n')
                  navigator.clipboard?.writeText(report)
                  setCopiedReport(true)
                  setTimeout(() => setCopiedReport(false), 2000)
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-shield-600 hover:bg-shield-500 text-white rounded-lg transition-colors shrink-0"
              >
                {copiedReport ? (
                  <>
                    <Check size={13} className="text-emerald-300" />
                    <span>{tx("Copied report!")}</span>
                  </>
                ) : (
                  <>
                    <Copy size={13} />
                    <span>{tx("Copy report details")}</span>
                  </>
                )}
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2 border-t border-slate-700/40">
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                <p className="text-slate-500 text-[11px] uppercase tracking-wider font-semibold">{tx("Installed Version")}</p>
                <p className="text-white font-mono text-sm mt-0.5 font-medium">
                  {"v"}{versionInfo?.version || tx("Loading...")}
                </p>
              </div>

              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                <p className="text-slate-500 text-[11px] uppercase tracking-wider font-semibold">{tx("Build Commit")}</p>
                <p className="text-slate-300 font-mono text-sm mt-0.5">
                  {versionInfo?.commit || 'unknown'}
                </p>
              </div>

              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                <p className="text-slate-500 text-[11px] uppercase tracking-wider font-semibold">{tx("API Health")}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-emerald-400 text-sm font-medium">{tx("Online ({v})", { v: versionInfo?.status || 'ok' })}</span>
                </div>
              </div>

              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                <p className="text-slate-500 text-[11px] uppercase tracking-wider font-semibold">{tx("User Role")}</p>
                <p className="text-slate-300 text-sm mt-0.5 capitalize">{user?.role || tx("User")}</p>
              </div>

              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800 sm:col-span-2">
                <p className="text-slate-500 text-[11px] uppercase tracking-wider font-semibold">{tx("Client Environment")}</p>
                <p className="text-slate-400 font-mono text-xs mt-0.5 truncate" title={typeof navigator !== 'undefined' ? navigator.userAgent : ''}>
                  {typeof navigator !== 'undefined' ? navigator.userAgent : tx("Unknown")}
                </p>
              </div>
            </div>
          </div>

          <div className="border border-slate-700/50 rounded-xl p-4 bg-slate-800/40 flex items-center justify-between">
            <div>
              <p className="text-slate-200 text-sm font-medium">{tx("Reporting an issue on GitHub?")}</p>
              <p className="text-slate-400 text-xs mt-0.5">
                {tx("Paste the copied report into your issue description to help developers reproduce and fix issues quickly.")}
              </p>
            </div>
            <a
              href="https://github.com/rlnunez/OpenOptOut/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-shield-400 hover:text-shield-300 bg-slate-900 border border-slate-700 rounded-lg transition-colors shrink-0"
            >
              <ExternalLink size={13} />
              <span>{tx("GitHub Issues")}</span>
            </a>
          </div>
        </div>
      )}

      {/* Attribution & Legal Notice (AGPL-3.0 Section 7(b)) */}
      <div className="mt-8 border border-slate-700/40 rounded-xl p-4 bg-slate-900/40 text-xs text-slate-400 leading-relaxed">
        <p>
          {tx("Based on OpenOptOut by Robert Nunez and contributors")} —{' '}
          <a
            href="https://github.com/rlnunez/Privacy-Shield"
            target="_blank"
            rel="noopener noreferrer"
            className="text-shield-400 hover:underline"
          >
            https://github.com/rlnunez/Privacy-Shield
          </a>
          {'. '}
          {tx("Includes work from the projects listed in")}{' '}
          <a
            href="https://github.com/rlnunez/Privacy-Shield/blob/main/CREDITS.md"
            target="_blank"
            rel="noopener noreferrer"
            className="text-shield-400 hover:underline font-medium"
          >
            CREDITS.md
          </a>
          {'.'}
        </p>
      </div>

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
