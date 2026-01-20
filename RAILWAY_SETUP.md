# Connecting All Apps with Shared PostgreSQL Database

This guide shows how to set up a shared PostgreSQL database on Railway so that all three apps (Admin Dashboard, VA Portal, Lifeline Home Buyers) can share user authentication.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Railway PostgreSQL                        │
│                   (Shared Database)                         │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Admin Dashboard│   │  VA Portal   │   │Lifeline Home │
│  (Streamlit)  │   │ (Streamlit)  │   │   Buyers     │
│    Local      │   │   Railway    │   │  (FastAPI)   │
└───────────────┘   └───────────────┘   └───────────────┘
```

## Step 1: Create PostgreSQL Database on Railway

1. Go to [Railway](https://railway.app) and log in
2. Open your project (or create a new one)
3. Click "New" → "Database" → "PostgreSQL"
4. Railway will create a PostgreSQL instance
5. Click on the PostgreSQL service to view its details

## Step 2: Get the Database URL

1. In the PostgreSQL service, click on "Variables"
2. Copy the `DATABASE_URL` value
   - It looks like: `postgresql://postgres:PASSWORD@HOST:PORT/railway`

## Step 3: Configure VA Portal on Railway

1. Open your VA Portal service on Railway
2. Go to "Variables"
3. Add a new variable:
   - Name: `DATABASE_URL`
   - Value: (paste the PostgreSQL URL from step 2)
4. Redeploy the service

## Step 4: Configure Local Admin Dashboard

Add the DATABASE_URL to your local environment:

### Option A: Environment Variable
```bash
export DATABASE_URL="postgresql://postgres:PASSWORD@HOST:PORT/railway"
```

### Option B: .env file
Create or edit `/Users/willyshumbusho/columbus-wholesaling/.env`:
```
DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway
```

### Option C: Streamlit Secrets
Create `/Users/willyshumbusho/columbus-wholesaling/.streamlit/secrets.toml`:
```toml
DATABASE_URL = "postgresql://postgres:PASSWORD@HOST:PORT/railway"
```

## Step 5: Install Dependencies

```bash
# For local admin dashboard
cd /Users/willyshumbusho/columbus-wholesaling
pip install psycopg2-binary

# For aerial-leads (if running locally)
cd /Users/willyshumbusho/aerial-leads
pip install psycopg2-binary
```

## Step 6: Migrate Existing Users (Optional)

If you have existing users in CSV files, you can migrate them to the database:

```python
from auth.database import DatabaseAuth

db_auth = DatabaseAuth()

# Migrate from auth_users.csv
migrated, skipped = db_auth.migrate_from_csv('/path/to/data/auth_users.csv')
print(f"Migrated: {migrated}, Skipped: {skipped}")
```

## Step 7: Test the Connection

### Test Locally
```python
from auth.database import DatabaseAuth

db_auth = DatabaseAuth()
print(f"Database type: {db_auth.db_type}")
print(f"Users: {db_auth.get_all_users()}")
```

### Test Login
1. Start your local admin dashboard
2. Create a new user in User Management
3. Check that the user appears in the database
4. Try logging into the Railway VA Portal with the new credentials

## Troubleshooting

### "Database auth unavailable" error
- Make sure `psycopg2-binary` is installed
- Verify the `DATABASE_URL` is set correctly
- Check that the Railway PostgreSQL service is running

### Users created locally don't appear on Railway
- Verify DATABASE_URL is the same on both local and Railway
- Check that the database connection is working (no firewall issues)
- Make sure you're creating users while connected to the database

### Connection timeout
- Railway PostgreSQL may have connection limits
- Try using connection pooling or reducing concurrent connections
- Check Railway dashboard for database health

## Default Admin Credentials

When the database is first created, a default admin user is created:
- Username: `admin`
- Password: `admin123`

**Change this immediately after first login!**

## Security Notes

1. Never commit DATABASE_URL to git
2. Add `.env` to `.gitignore`
3. Change the default admin password immediately
4. Use strong passwords for all users
5. Consider enabling SSL for database connections in production
