const { Client } = require('pg');

const client = new Client({
  host: 'shuttle.proxy.rlwy.net',
  port: 49946,
  database: 'railway',
  user: 'postgres',
  password: 'bMlnUcJtayTOgxAcNcXGQLubTqXflCAu',
  ssl: { rejectUnauthorized: false }
});

async function getSampleData() {
  await client.connect();
  
  const tables = ['users', 'lead_assignments', 'inbound_leads', 'activity_log', 'sessions', 'va_applications'];
  
  for (const tableName of tables) {
    console.log('\n' + '='.repeat(80));
    console.log('SAMPLE DATA FROM: ' + tableName);
    console.log('='.repeat(80));
    
    let query = 'SELECT * FROM "' + tableName + '" LIMIT 3';
    
    // Exclude sensitive/binary data
    if (tableName === 'users') {
      query = 'SELECT id, username, full_name, email, role, status, created_at, last_login, phone FROM users LIMIT 3';
    }
    if (tableName === 'va_applications') {
      query = 'SELECT id, status, full_name, email, phone, country, timezone, years_experience, cold_calling_experience, created_at FROM va_applications LIMIT 3';
    }
    
    try {
      const result = await client.query(query);
      for (const row of result.rows) {
        console.log('\n--- Row ---');
        for (const [key, value] of Object.entries(row)) {
          let displayVal = value;
          if (value instanceof Date) {
            displayVal = value.toISOString();
          } else if (typeof value === 'string' && value.length > 100) {
            displayVal = value.substring(0, 100) + '...';
          }
          console.log('  ' + key + ': ' + displayVal);
        }
      }
    } catch (e) {
      console.log('Error: ' + e.message);
    }
  }
  
  await client.end();
}

getSampleData().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
