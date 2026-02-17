# Lifeline Home Buyers - Complete System Documentation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED POSTGRESQL DATABASE                    │
│                    (Railway - Single Source of Truth)            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   users     │  │  sessions   │  │    inbound_leads        │  │
│  │  (VAs/Admin)│  │  (logins)   │  │  (from public site)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                    │                      │
         ▼                    ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│  ADMIN DASHBOARD │  │   VA PORTAL     │  │ LIFELINE HOME BUYERS│
│  (Your Computer) │  │   (Railway)     │  │     (Railway)       │
│                  │  │                 │  │                     │
│  localhost:8501  │  │ aerial-leads-   │  │ celebrated-alignment│
│                  │  │ production.up.  │  │ .up.railway.app     │
│                  │  │ railway.app     │  │                     │
└─────────────────┘  └─────────────────┘  └─────────────────────┘
      YOU                  VAs              MOTIVATED SELLERS
```

---

## 1. ADMIN DASHBOARD (Your Local Computer)

**Location:** `columbus-wholesaling/dashboard.py`
**URL:** http://localhost:8501

### Features:

#### 📊 Lead Generation
| Feature | What it does |
|---------|--------------|
| **Tax Delinquent Scraper** | Scrapes Franklin County for properties behind on taxes |
| **Probate Scraper** | Finds inherited properties from court records |
| **Sheriff Sale Scraper** | Finds pre-foreclosure properties |
| **Code Violations** | Properties with city violations (neglected) |
| **Motivation Scoring** | Scores leads 0-100 based on distress signals |

#### 📞 Outreach Tools
| Feature | What it does |
|---------|--------------|
| **Call Tracker** | Log calls, outcomes, follow-ups |
| **SMS Campaigns** | Send text message campaigns to leads |
| **RVM Manager** | Ringless voicemail drops |
| **Direct Mail** | Track mail campaigns |
| **Follow-up Sequences** | Automated multi-touch sequences |

#### 💼 Deal Management
| Feature | What it does |
|---------|--------------|
| **Deal Pipeline** | Track deals: Lead → Qualified → Offer → Contract → Closed |
| **Appointments** | Schedule walkthroughs, signings, closings |
| **Buyer Matcher** | Match deals to cash buyers in your database |

#### 👥 Team Management
| Feature | What it does |
|---------|--------------|
| **User Management** | Create VAs, admins, set roles |
| **VA Management** | Assign leads, track performance |
| **📥 Inbound Leads** | See leads from your public website |

---

## 2. VA PORTAL (Railway)

**Location:** `aerial-leads/va_dashboard.py`
**URL:** https://aerial-leads-production.up.railway.app

### What VAs See:

| Feature | What it does |
|---------|--------------|
| **My Stats** | Their calls, contacts, appointments today |
| **My Leads** | Leads assigned to them |
| **Dialer** | Click-to-call interface |
| **Callback Queue** | RVM callbacks to handle |
| **Call Tracker** | Log their call outcomes |
| **Inbound Leads** | Hot leads from website |

### How it connects:
- VA logs in → checks **shared PostgreSQL** for credentials
- You create VA in Admin → they can immediately login on Railway
- Their call logs sync back to your admin view

---

## 3. LIFELINE HOME BUYERS (Railway)

**Location:** `aerial-leads/public_site/app.py`
**URL:** https://celebrated-alignment.up.railway.app

### Purpose: SEO & Inbound Lead Capture

| Page | What it does |
|------|--------------|
| **Homepage** | "We Buy Houses" landing page |
| **Property Pages** | Individual pages for each distressed property (SEO) |
| **Get Offer** | Form for sellers to request cash offer |
| **Calculator** | Interactive offer calculator (lead magnet) |
| **Probate Page** | Landing page for inherited properties |
| **Tax Delinquent Page** | Landing page for tax-behind sellers |
| **Property Database** | Searchable map of distressed properties |

### How it connects:
- Seller finds you on Google → fills out form
- Lead saved to **shared PostgreSQL**
- Appears in your Admin → **📥 Inbound Leads**
- You assign to VA → they call back

---

## 4. DATA FLOW

### Outbound (You finding sellers):
```
Scrape Data → Score Leads → Assign to VA → VA Calls → Log Outcome → Deal Pipeline
```

### Inbound (Sellers finding you):
```
Google Search → Your Public Site → Form Submit → Database → Admin Dashboard → VA Calls Back
```

---

## 5. USER ROLES

| Role | Access |
|------|--------|
| **Admin** | Everything - all pages, all data, user management |
| **Manager** | Lead management, VA oversight, reports |
| **VA** | Only their assigned leads, call logging, limited view |

---

## 6. KEY FILES

| File | Purpose |
|------|---------|
| `auth/database.py` | Shared PostgreSQL authentication |
| `auth/va_auth.py` | CSV-based auth (fallback) |
| `tracking/va_manager.py` | VA assignment & performance |
| `tracking/deal_pipeline.py` | Deal stages & tracking |
| `buyers/buyer_matcher.py` | Match deals to cash buyers |
| `marketing/sms_campaigns.py` | Text message campaigns |
| `public_site/app.py` | SEO website for sellers |

---

## 7. THE MONEY FLOW

```
1. FIND MOTIVATED SELLERS
   - Scrape tax/probate/violations → OR → Sellers find YOU via SEO

2. MAKE CONTACT
   - VAs cold call → OR → Seller submits form (inbound)

3. QUALIFY & OFFER
   - Walkthrough → ARV/Repair estimate → Make offer

4. GET CONTRACT
   - Seller accepts → Under contract

5. FIND BUYER
   - Buyer Matcher → Blast to cash buyers → Assign deal

6. CLOSE & COLLECT
   - Assignment fee ($5k-$20k) → OR → Double close
```

---

## 8. DATABASE CONFIGURATION

### Railway PostgreSQL
- **Internal URL:** `postgresql://postgres:PASSWORD@postgres.railway.internal:5432/railway`
- **Public URL:** `postgresql://postgres:PASSWORD@shuttle.proxy.rlwy.net:PORT/railway`

### Local Setup
Create `.env` file in `columbus-wholesaling/`:
```
DATABASE_URL=postgresql://postgres:PASSWORD@shuttle.proxy.rlwy.net:PORT/railway
```

### Database Tables
- `users` - VA and admin accounts
- `sessions` - Login sessions
- `activity_log` - User activity tracking
- `inbound_leads` - Leads from public website

---

## 9. DEPLOYMENT

| App | Platform | Auto-Deploy |
|-----|----------|-------------|
| Admin Dashboard | Local (your computer) | Manual start |
| VA Portal | Railway | Yes (on git push) |
| Lifeline Home Buyers | Railway | Yes (on git push) |
| PostgreSQL | Railway | Always running |

### Start Admin Dashboard:
```bash
cd columbus-wholesaling
python3 -m streamlit run dashboard.py --server.port 8501
```

---

## 10. FUTURE FEATURES (TODO)

- [ ] **Contracts & Documents**
  - Contract templates (Purchase Agreement, Assignment)
  - E-signatures integration
  - Document storage per deal
  - Auto-fill from deal data
  - Contract status tracking

---

## 11. VA RECRUITING SYSTEM (spectacular-reverence)

**Location:** `recruiting/application_page.py`
**URL:** https://spectacular-reverence-production.up.railway.app

### Purpose
Public job application portal for hiring Virtual Assistants from multiple countries.

### How It Works

```
1. Applicant visits careers page
2. Selects their country → sees salary in local currency
3. Fills out application form
4. Submits → saved to PostgreSQL
5. Confirmation email sent via SendGrid
6. Admin reviews in Recording Page
7. Admin assigns cold call script
8. Applicant records video practicing the script
9. Admin reviews video
10. If approved → personal interview
11. Decision: hired or rejected
```

### Supported Countries & Salaries

| Country | Currency | Monthly Salary |
|---------|----------|----------------|
| Rwanda | RWF | 210,000 |
| Uganda | UGX | 500,000 |
| Kenya | KES | 20,000 |
| Tanzania | TZS | 375,000 |
| Burundi | BIF | 450,000 |
| Philippines | PHP | 10,000 |
| India | INR | 12,500 |
| Pakistan | PKR | 42,000 |
| Bangladesh | BDT | 18,000 |
| Nepal | NPR | 20,000 |
| Sri Lanka | LKR | 48,000 |
| South Africa | ZAR | 2,800 |
| Ghana | GHS | 2,400 |
| Nigeria | NGN | 230,000 |

### Application Statuses

| Status | Meaning |
|--------|---------|
| `applied` | Just submitted |
| `reviewing` | Under review |
| `script_sent` | Cold call script assigned |
| `video_submitted` | Video received |
| `video_approved` | Ready for interview |
| `interview` | Interview scheduled |
| `hired` | Accepted |
| `rejected` | Not accepted |
| `withdrawn` | Applicant withdrew |

### Cold Call Scripts

1. **Tax Delinquent** - For calling property owners behind on taxes
2. **Probate** - For calling inherited property owners
3. **Tired Landlord** - For calling overwhelmed landlords

### Key Files

| File | Purpose |
|------|---------|
| `recruiting/application_page.py` | Public application form |
| `recruiting/va_applications.py` | Backend logic & database |
| `recruiting/email_notifications.py` | SendGrid email functions |
| `recruiting/recording_page.py` | Admin review interface |
| `va_app_runner.py` | Railway entry point |

### Environment Variables (spectacular-reverence)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (use `${{Postgres.DATABASE_URL}}`) |
| `SENDGRID_API_KEY` | SendGrid API key |
| `SENDGRID_FROM_EMAIL` | Sender email (admin@areliga.com) |
| `SENDGRID_FROM_NAME` | Sender name (Lifeline Home Buyers) |

### Start Command
```
python va_app_runner.py
```

---

## Summary

This is a **full wholesaling operation system**:
- **Lead Gen**: Scrape distressed properties
- **SEO**: Sellers find you on Google
- **CRM**: Track every lead and deal
- **Team**: VAs work remotely via portal
- **Buyers**: Match deals to your buyer list
- **All Connected**: One database, three apps, everything syncs
