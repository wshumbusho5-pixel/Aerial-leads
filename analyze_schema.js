const { Client } = require('pg');

const client = new Client({
  host: 'shuttle.proxy.rlwy.net',
  port: 49946,
  database: 'railway',
  user: 'postgres',
  password: 'bMlnUcJtayTOgxAcNcXGQLubTqXflCAu',
  ssl: { rejectUnauthorized: false }
});

async function analyzeSchema() {
  await client.connect();
  
  const tablesQuery = `
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_type = 'BASE TABLE'
    ORDER BY table_name;
  `;
  
  const tables = await client.query(tablesQuery);
  console.log('='.repeat(80));
  console.log('DATABASE SCHEMA ANALYSIS - Real Estate Wholesaling Lead Generation System');
  console.log('='.repeat(80));
  console.log('\nTotal Tables Found: ' + tables.rows.length + '\n');
  
  for (const table of tables.rows) {
    const tableName = table.table_name;
    console.log('\n' + '='.repeat(80));
    console.log('TABLE: ' + tableName);
    console.log('='.repeat(80));
    
    const columnsQuery = `
      SELECT 
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = $1
      ORDER BY ordinal_position;
    `;
    
    const columns = await client.query(columnsQuery, [tableName]);
    
    console.log('\nColumns:');
    console.log('-'.repeat(80));
    for (const col of columns.rows) {
      let dataType = col.data_type;
      if (col.character_maximum_length) {
        dataType += '(' + col.character_maximum_length + ')';
      }
      const nullable = col.is_nullable === 'YES' ? 'NULL' : 'NOT NULL';
      let defaultVal = '';
      if (col.column_default) {
        const defStr = String(col.column_default);
        defaultVal = ' DEFAULT ' + (defStr.length > 40 ? defStr.substring(0, 40) + '...' : defStr);
      }
      console.log('  ' + col.column_name.padEnd(30) + ' ' + dataType.padEnd(25) + ' ' + nullable + defaultVal);
    }
    
    const countQuery = 'SELECT COUNT(*) as count FROM "' + tableName + '"';
    try {
      const countResult = await client.query(countQuery);
      console.log('\nRow Count: ' + countResult.rows[0].count);
    } catch (e) {
      console.log('\nRow Count: Unable to count');
    }
    
    const fkQuery = `
      SELECT
        kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
      FROM information_schema.table_constraints AS tc
      JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
      JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
      WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_name = $1;
    `;
    
    const fks = await client.query(fkQuery, [tableName]);
    if (fks.rows.length > 0) {
      console.log('\nForeign Keys:');
      for (const fk of fks.rows) {
        console.log('  ' + fk.column_name + ' -> ' + fk.foreign_table_name + '(' + fk.foreign_column_name + ')');
      }
    }
    
    const indexQuery = `
      SELECT indexname, indexdef
      FROM pg_indexes
      WHERE tablename = $1 AND schemaname = 'public';
    `;
    
    const indexes = await client.query(indexQuery, [tableName]);
    if (indexes.rows.length > 0) {
      console.log('\nIndexes:');
      for (const idx of indexes.rows) {
        console.log('  ' + idx.indexname);
      }
    }
  }
  
  await client.end();
}

analyzeSchema().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
