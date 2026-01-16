"""
Aerial Leads - Command-Line Interface

Beautiful CLI using Click and Rich for terminal operations.
Supports multiple markets via --market parameter.
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track, Progress, SpinnerColumn, BarColumn, TextColumn
from rich import print as rprint
from pathlib import Path
import pandas as pd

from shared.config.settings import VERSION, APP_NAME
from shared.config.market_loader import MarketLoader, load_market, list_markets
from sellers.scrapers.factory import ScraperFactory, get_scrapers_for_market
from sellers.scrapers.franklin_county import FranklinCountyScraper, create_sample_data
from shared.data_processing.aggregator import LeadAggregator
from shared.config.logging_config import log_success, log_failure

console = Console()

# Default market for backward compatibility
DEFAULT_MARKET = 'columbus_oh'


@click.group()
@click.version_option(version=VERSION, prog_name=APP_NAME)
def cli():
    """
    🏠 Aerial Leads - Premium Real Estate Lead Generation

    Transform tax delinquency data into high-value investment opportunities.
    """
    # Show banner
    console.print(Panel.fit(
        f"[bold cyan]{APP_NAME}[/bold cyan] v{VERSION}\n"
        "[dim]Premium Real Estate Lead Generation[/dim]",
        border_style="cyan"
    ))


# ========================================
# SCRAPING COMMANDS
# ========================================

@cli.command()
@click.option('--max-results', default=200, help='Maximum properties to scrape')
@click.option('--min-years', default=2, help='Minimum years tax delinquent')
@click.option('--property-type', default='residential', help='Property type filter')
@click.option('--output', default='tax_data.csv', help='Output filename')
@click.option('--sample', is_flag=True, help='Use sample data instead of real scraping')
def scrape(max_results, min_years, property_type, output, sample):
    """Scrape tax delinquent properties from Franklin County"""

    console.print("\n[bold green]🔍 Scraping Franklin County Tax Data[/bold green]\n")

    console.print(f"[cyan]Settings:[/cyan]")
    console.print(f"  • Max results: {max_results}")
    console.print(f"  • Min years delinquent: {min_years}")
    console.print(f"  • Property type: {property_type}")
    console.print(f"  • Sample mode: {sample}\n")

    scraper = FranklinCountyScraper()

    if sample:
        console.print("[yellow]Using sample data (for testing)[/yellow]")
        properties = create_sample_data()
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Scraping properties...", total=None)

            properties = scraper.scrape(
                delinquent_only=True,
                min_years_delinquent=min_years,
                property_type=property_type,
                max_results=max_results
            )

            progress.update(task, completed=True)

    # Export
    path = scraper.export_to_csv(properties, output)

    # Show summary
    console.print(f"\n[bold green]✅ Success![/bold green]")
    console.print(f"Scraped {len(properties)} properties")
    console.print(f"Exported to: [cyan]{path}[/cyan]\n")


@cli.command()
@click.argument('input_file')
@click.option('--max-properties', default=200, help='Max properties to process')
@click.option('--min-score', default=40, help='Minimum motivation score')
@click.option('--output', default='premium_leads.csv', help='Output filename')
def generate(input_file, max_properties, min_score, output):
    """Generate complete lead dataset from scratch"""

    console.print("\n[bold magenta]🚀 Full Lead Generation Pipeline[/bold magenta]\n")

    aggregator = LeadAggregator()

    with console.status("[bold green]Generating leads...") as status:
        leads_df = aggregator.generate_leads(
            max_properties=max_properties,
            min_motivation_score=min_score
        )

    if leads_df.empty:
        log_failure("No leads generated")
        return

    # Export
    path = aggregator.export_leads(leads_df, output)

    # Show summary
    stats = aggregator.generate_summary_stats(leads_df)

    table = Table(title="Lead Generation Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    table.add_row("Total Leads", str(stats['total_leads']))
    table.add_row("Tier 1 (80-100)", str(stats['tier_1_count']))
    table.add_row("Tier 2 (60-79)", str(stats['tier_2_count']))
    table.add_row("Tier 3 (40-59)", str(stats['tier_3_count']))
    table.add_row("Avg Motivation Score", f"{stats['avg_motivation_score']:.1f}")
    table.add_row("Avg Taxes Owed", f"${stats['avg_taxes_owed']:,.0f}")
    table.add_row("Phone Numbers Found", str(stats['phone_available_count']))

    console.print("\n")
    console.print(table)
    console.print(f"\n[bold green]✅ Leads exported to:[/bold green] [cyan]{path}[/cyan]\n")


@cli.command()
@click.argument('input_file')
@click.option('--output', default='enriched_leads.csv', help='Output filename')
def enrich(input_file, output):
    """Enrich existing CSV with skip tracing and scoring"""

    console.print(f"\n[bold blue]📊 Enriching data from {input_file}[/bold blue]\n")

    aggregator = LeadAggregator()

    with console.status("[bold green]Enriching data...") as status:
        enriched_df = aggregator.load_and_enrich(input_file)

    path = aggregator.export_leads(enriched_df, output)

    log_success(f"Enriched {len(enriched_df)} properties")
    console.print(f"Exported to: [cyan]{path}[/cyan]\n")


@cli.command()
@click.argument('input_file')
def stats(input_file):
    """Show statistics for a lead dataset"""

    console.print(f"\n[bold cyan]📈 Dataset Statistics[/bold cyan]\n")

    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        log_failure(f"Could not read file: {e}")
        return

    aggregator = LeadAggregator()
    stats = aggregator.generate_summary_stats(df)

    # Create stats table
    table = Table(title=f"Statistics for {Path(input_file).name}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", justify="right", style="green", width=20)

    table.add_row("Total Properties", str(stats['total_leads']))
    table.add_row("", "")  # Spacer
    table.add_row("[bold]By Tier", "")
    table.add_row("  Tier 1 (80-100)", f"{stats['tier_1_count']} (${stats['tier_1_count'] * 100:,})")
    table.add_row("  Tier 2 (60-79)", f"{stats['tier_2_count']} (${stats['tier_2_count'] * 75:,})")
    table.add_row("  Tier 3 (40-59)", f"{stats['tier_3_count']} (${stats['tier_3_count'] * 50:,})")
    table.add_row("  Tier 4 (<40)", str(stats['tier_4_count']))
    table.add_row("", "")  # Spacer
    table.add_row("[bold]Scoring", "")
    table.add_row("  Avg Motivation Score", f"{stats['avg_motivation_score']:.1f}/100")
    table.add_row("  Avg Years Delinquent", f"{stats['avg_years_delinquent']:.1f}")
    table.add_row("  Avg Taxes Owed", f"${stats['avg_taxes_owed']:,.0f}")
    table.add_row("", "")  # Spacer
    table.add_row("[bold]Contact Data", "")
    table.add_row("  Skip Traced", str(stats['skip_traced_count']))
    table.add_row("  Phone Numbers", str(stats['phone_available_count']))
    table.add_row("", "")  # Spacer
    table.add_row("[bold]Financial", "")
    table.add_row("  Total Property Value", f"${stats['total_potential_value']:,.0f}")
    table.add_row("  Total Taxes Owed", f"${stats['total_taxes_owed']:,.0f}")

    console.print(table)
    console.print()


@cli.command()
@click.argument('input_file')
@click.option('--tier', type=int, help='Export specific tier only')
def export(input_file, tier):
    """Export leads by tier"""

    console.print(f"\n[bold yellow]📤 Exporting Leads[/bold yellow]\n")

    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        log_failure(f"Could not read file: {e}")
        return

    aggregator = LeadAggregator()

    if tier:
        # Export specific tier
        tier_df = df[df['tier'] == tier]
        if tier_df.empty:
            log_failure(f"No leads found for tier {tier}")
            return

        path = aggregator.export_leads(tier_df, f'tier_{tier}_leads.csv')
        log_success(f"Exported {len(tier_df)} Tier {tier} leads to {path}")
    else:
        # Export all tiers separately
        tier_files = aggregator.export_by_tier(df)

        console.print("[bold green]✅ Exported by tier:[/bold green]")
        for tier_num, path in tier_files.items():
            console.print(f"  Tier {tier_num}: [cyan]{path}[/cyan]")

    console.print()


@cli.command()
@click.argument('input_file')
@click.option('--top', default=10, help='Number of top leads to display')
def top(input_file, top):
    """Show top leads by motivation score"""

    console.print(f"\n[bold magenta]⭐ Top {top} Leads by Motivation Score[/bold magenta]\n")

    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        log_failure(f"Could not read file: {e}")
        return

    # Get top leads
    top_leads = df.nlargest(top, 'motivation_score')

    # Create table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="cyan", width=5)
    table.add_column("Address", style="white", width=30)
    table.add_column("Score", justify="center", style="green", width=6)
    table.add_column("Tier", justify="center", style="yellow", width=5)
    table.add_column("Taxes Owed", justify="right", style="red", width=11)
    table.add_column("Year Built", justify="center", style="magenta", width=10)
    table.add_column("Phone", style="blue", width=14)

    for i, (idx, row) in enumerate(top_leads.iterrows(), 1):
        year_built = str(int(row['year_built'])) if 'year_built' in row and pd.notna(row['year_built']) and row['year_built'] > 0 else 'N/A'
        table.add_row(
            str(i),
            row['address'][:28] + "..." if len(row['address']) > 30 else row['address'],
            str(int(row['motivation_score'])),
            str(row['tier']),
            f"${row['taxes_owed']:,.0f}",
            year_built,
            row.get('phone', 'N/A')
        )

    console.print(table)
    console.print()


@cli.command()
@click.argument('name')
@click.option('--file', '-f', default=None, help='CSV file to search (searches all processed files if not specified)')
@click.option('--exact', is_flag=True, help='Exact match only (default is partial match)')
def search(name, file, exact):
    """Search for a person by owner name"""

    console.print(f"\n[bold cyan]🔍 Searching for: \"{name}\"[/bold cyan]\n")

    # Find files to search
    files_to_search = []

    if file:
        files_to_search = [Path(file)]
    else:
        # Search all CSV files in processed directory
        from shared.config.settings import PROCESSED_DATA_DIR
        files_to_search = list(PROCESSED_DATA_DIR.glob('*.csv'))

        if not files_to_search:
            log_failure("No CSV files found in data/processed/")
            return

    all_results = []

    for csv_file in files_to_search:
        try:
            df = pd.read_csv(csv_file)

            if 'owner_name' not in df.columns:
                continue

            # Search by owner name
            if exact:
                matches = df[df['owner_name'].str.lower() == name.lower()]
            else:
                matches = df[df['owner_name'].str.lower().str.contains(name.lower(), na=False)]

            if not matches.empty:
                matches = matches.copy()
                matches['source_file'] = csv_file.name
                all_results.append(matches)

        except Exception as e:
            console.print(f"[dim]Could not read {csv_file.name}: {e}[/dim]")

    if not all_results:
        console.print(f"[yellow]No results found for \"{name}\"[/yellow]")
        console.print(f"[dim]Searched {len(files_to_search)} file(s)[/dim]\n")
        return

    # Combine results
    results_df = pd.concat(all_results, ignore_index=True)

    # Remove duplicates based on address (same lead might be in multiple files)
    if 'address' in results_df.columns:
        results_df = results_df.drop_duplicates(subset=['address'], keep='first')

    console.print(f"[green]Found {len(results_df)} result(s)[/green]\n")

    # Display results
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Owner Name", style="green", width=22)
    table.add_column("Address", style="white", width=30)
    table.add_column("Score", justify="center", style="yellow", width=6)
    table.add_column("Taxes Owed", justify="right", style="red", width=11)
    table.add_column("Year Built", justify="center", style="magenta", width=10)
    table.add_column("Phone", style="blue", width=14)

    for i, (idx, row) in enumerate(results_df.iterrows(), 1):
        owner = str(row.get('owner_name', 'N/A'))[:20]
        address = str(row.get('address', 'N/A'))[:28]
        score = str(int(row['motivation_score'])) if 'motivation_score' in row and pd.notna(row['motivation_score']) else 'N/A'
        taxes = f"${row['taxes_owed']:,.0f}" if 'taxes_owed' in row and pd.notna(row['taxes_owed']) else 'N/A'
        year_built = str(int(row['year_built'])) if 'year_built' in row and pd.notna(row['year_built']) and row['year_built'] > 0 else 'N/A'
        phone = str(row.get('phone', 'N/A')) if pd.notna(row.get('phone')) else 'N/A'

        table.add_row(str(i), owner, address, score, taxes, year_built, phone)

        # Limit display to 20 results
        if i >= 20:
            console.print(f"[dim]...and {len(results_df) - 20} more results[/dim]")
            break

    console.print(table)

    # Show detailed view option
    if len(results_df) > 0:
        console.print(f"\n[dim]Tip: Use --file to search a specific CSV file[/dim]")

    console.print()


@cli.command()
def dashboard():
    """Launch web dashboard (placeholder)"""
    console.print("\n[yellow]📊 Web dashboard coming soon![/yellow]")
    console.print("[dim]Run: python -m web.app to start the dashboard[/dim]\n")


@cli.command()
def version():
    """Show version information"""
    console.print(f"\n[bold cyan]{APP_NAME}[/bold cyan] version [green]{VERSION}[/green]")
    console.print("[dim]Premium Real Estate Lead Generation Platform[/dim]\n")


# ========================================
# MARKET COMMANDS
# ========================================

@cli.command()
def markets():
    """List available markets"""

    console.print("\n[bold cyan]📍 Available Markets[/bold cyan]\n")

    loader = MarketLoader()
    market_info = loader.get_market_info()

    if not market_info:
        console.print("[yellow]No markets configured. Add YAML files to config/markets/[/yellow]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="green", width=15)
    table.add_column("Name", style="white", width=25)
    table.add_column("County", style="yellow", width=15)
    table.add_column("State", style="cyan", width=6)
    table.add_column("Zip Codes", justify="right", style="magenta", width=10)

    for info in market_info:
        table.add_row(
            info['id'],
            info['name'],
            info['county'],
            info['state'],
            str(info['zip_count'])
        )

    console.print(table)
    console.print(f"\n[dim]Use --market <id> with other commands to target a specific market.[/dim]")
    console.print(f"[dim]Default market: {DEFAULT_MARKET}[/dim]\n")


@cli.command(name='market-info')
@click.argument('market_id')
def market_info(market_id):
    """Show detailed information about a market"""

    console.print(f"\n[bold cyan]📍 Market Details: {market_id}[/bold cyan]\n")

    try:
        market = load_market(market_id)
    except ValueError as e:
        log_failure(str(e))
        return

    # Basic info
    console.print(f"[bold]Name:[/bold] {market.name}")
    console.print(f"[bold]County:[/bold] {market.county}")
    console.print(f"[bold]State:[/bold] {market.state}")
    console.print(f"[bold]Timezone:[/bold] {market.timezone}")

    # Data sources
    console.print(f"\n[bold cyan]Tax Data Source[/bold cyan]")
    console.print(f"  Type: {market.tax_data.type}")
    console.print(f"  Source: {market.tax_data.source}")
    if market.tax_data.urls:
        console.print(f"  URLs: {list(market.tax_data.urls.keys())}")

    console.print(f"\n[bold cyan]Violations Data Source[/bold cyan]")
    console.print(f"  Type: {market.violations.type}")
    if market.violations.url:
        console.print(f"  URL: {market.violations.url[:60]}...")

    # Scoring
    console.print(f"\n[bold cyan]Scoring Configuration[/bold cyan]")
    console.print(f"  Annual Tax Rate: {market.scoring.estimated_annual_tax_rate:.1%}")
    console.print(f"  High Debt Ratio: {market.scoring.tax_debt_ratio.get('high', 0.20):.0%}")

    # Data Quality
    console.print(f"\n[bold cyan]Data Quality Filters[/bold cyan]")
    console.print(f"  Min Amount Owed: ${market.data_quality.min_amount_owed:,.0f}")
    console.print(f"  Min Years Delinquent: {market.data_quality.min_years_delinquent}")

    # Zip codes
    console.print(f"\n[bold cyan]Coverage[/bold cyan]")
    console.print(f"  Zip Codes: {len(market.zip_codes)}")
    console.print(f"  Sample: {', '.join(market.zip_codes[:5])}...")

    console.print()


@cli.command(name='generate-market')
@click.option('--market', '-m', default=DEFAULT_MARKET, help='Market ID (e.g., columbus_oh)')
@click.option('--max-properties', default=200, help='Maximum properties to process')
@click.option('--min-amount', default=None, type=float, help='Minimum taxes owed (uses market default)')
@click.option('--min-years', default=None, type=int, help='Minimum years delinquent (uses market default)')
@click.option('--output', default=None, help='Output filename (auto-generated if not specified)')
def generate_market(market, max_properties, min_amount, min_years, output):
    """Generate leads for a specific market using market configuration"""

    console.print(f"\n[bold magenta]🚀 Generating Leads for Market: {market}[/bold magenta]\n")

    # Load market config
    try:
        market_config = load_market(market)
    except ValueError as e:
        log_failure(str(e))
        console.print(f"\n[dim]Available markets: {list_markets()}[/dim]")
        return

    console.print(f"[cyan]Market:[/cyan] {market_config.display_name}")
    console.print(f"[cyan]Tax Data Type:[/cyan] {market_config.tax_data.type}")
    console.print(f"[cyan]Violations Type:[/cyan] {market_config.violations.type}")

    # Get scrapers
    try:
        tax_scraper = ScraperFactory.create_tax_scraper(market_config)
        violations_scraper = ScraperFactory.create_violations_scraper(market_config)
    except Exception as e:
        log_failure(f"Could not create scrapers: {e}")
        return

    console.print(f"\n[green]✓ Tax Scraper:[/green] {type(tax_scraper).__name__}")
    console.print(f"[green]✓ Violations Scraper:[/green] {type(violations_scraper).__name__ if violations_scraper else 'None'}")

    # Load tax data
    console.print(f"\n[bold]Loading tax delinquent properties...[/bold]")

    try:
        with console.status("[bold green]Loading data..."):
            properties_df = tax_scraper.load_tax_delinquent_properties(
                min_amount_owed=min_amount,
                min_years_delinquent=min_years,
                max_properties=max_properties
            )
    except FileNotFoundError as e:
        log_failure(f"Data files not found: {e}")
        console.print(f"\n[yellow]Please place data files in: data/raw/{market}/[/yellow]")
        return
    except Exception as e:
        log_failure(f"Error loading data: {e}")
        return

    if properties_df.empty:
        log_failure("No properties found matching criteria")
        return

    console.print(f"[green]✓ Loaded {len(properties_df)} properties[/green]")

    # Enrich with violations (if available)
    if violations_scraper and not properties_df.empty:
        console.print(f"\n[bold]Enriching with code violations...[/bold]")
        try:
            parcel_numbers = properties_df['parcel_id'].tolist()
            with console.status("[bold green]Querying violations API..."):
                violations = violations_scraper.get_violations_by_parcel(parcel_numbers[:100])  # Limit API calls

            if violations:
                violations_df = violations_scraper.aggregate_violations_by_parcel(violations)
                properties_df = properties_df.merge(
                    violations_df[['parcel_number', 'total_violations', 'critical_violations']],
                    left_on='parcel_id',
                    right_on='parcel_number',
                    how='left'
                )
                properties_df['total_violations'] = properties_df['total_violations'].fillna(0).astype(int)
                properties_df['code_violations'] = properties_df['total_violations']
                console.print(f"[green]✓ Found violations for {len(violations)} properties[/green]")
            else:
                properties_df['code_violations'] = 0
                console.print("[yellow]No violations found[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Could not fetch violations: {e}[/yellow]")
            properties_df['code_violations'] = 0
    else:
        properties_df['code_violations'] = 0

    # Score properties
    console.print(f"\n[bold]Scoring properties...[/bold]")
    from scoring.motivation_scorer import MotivationScorer
    scorer = MotivationScorer()

    properties_df = scorer.score_dataframe(properties_df)
    console.print(f"[green]✓ Scored {len(properties_df)} properties[/green]")

    # Export
    output_filename = output or f"{market}_leads.csv"
    from shared.config.settings import PROCESSED_DATA_DIR
    output_path = PROCESSED_DATA_DIR / output_filename
    properties_df.to_csv(output_path, index=False)

    # Summary
    console.print(f"\n[bold green]✅ Lead Generation Complete![/bold green]")

    table = Table(title=f"Results for {market_config.name}", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    tier_1 = len(properties_df[properties_df['tier'] == 1]) if 'tier' in properties_df.columns else 0
    tier_2 = len(properties_df[properties_df['tier'] == 2]) if 'tier' in properties_df.columns else 0
    tier_3 = len(properties_df[properties_df['tier'] == 3]) if 'tier' in properties_df.columns else 0

    table.add_row("Total Properties", str(len(properties_df)))
    table.add_row("Tier 1 (80-100)", str(tier_1))
    table.add_row("Tier 2 (60-79)", str(tier_2))
    table.add_row("Tier 3 (40-59)", str(tier_3))
    if 'motivation_score' in properties_df.columns:
        table.add_row("Avg Score", f"{properties_df['motivation_score'].mean():.1f}")
    table.add_row("Avg Taxes Owed", f"${properties_df['taxes_owed'].mean():,.0f}")

    console.print("\n")
    console.print(table)
    console.print(f"\n[bold]Exported to:[/bold] [cyan]{output_path}[/cyan]\n")


if __name__ == '__main__':
    cli()
