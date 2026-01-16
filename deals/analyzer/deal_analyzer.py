#!/usr/bin/env python3
"""
Wholesale Deal Analyzer
Calculate MAO (Maximum Allowable Offer) and potential profit
"""

def analyze_deal():
    """Interactive deal analyzer for wholesale real estate"""

    print("=" * 60)
    print("          WHOLESALE DEAL ANALYZER")
    print("=" * 60)
    print()

    # Property Info
    print("PROPERTY INFORMATION")
    print("-" * 40)
    address = input("Property Address: ")

    # ARV Input
    print("\nARV (After Repair Value)")
    print("-" * 40)
    print("Tip: Check recent comps within 0.5 miles, similar sq ft")
    arv = float(input("Estimated ARV: $"))

    # Repair Costs
    print("\nREPAIR ESTIMATES")
    print("-" * 40)
    print("Quick estimates per sq ft:")
    print("  Light rehab: $10-20/sqft")
    print("  Medium rehab: $20-35/sqft")
    print("  Heavy rehab: $35-60/sqft")
    repairs = float(input("Estimated Repairs: $"))

    # Investor Criteria
    print("\nINVESTOR CRITERIA")
    print("-" * 40)
    print("Typical investor wants 70-75% of ARV")
    arv_percentage = float(input("Investor ARV % (e.g., 70): ")) / 100

    # Your Assignment Fee
    print("\nYOUR PROFIT")
    print("-" * 40)
    assignment_fee = float(input("Desired Assignment Fee: $"))

    # Calculations
    print("\n")
    print("=" * 60)
    print("          DEAL ANALYSIS RESULTS")
    print("=" * 60)
    print(f"\nProperty: {address}")
    print("-" * 60)

    # What investor will pay
    investor_max = arv * arv_percentage
    investor_offer = investor_max - repairs

    # Your MAO (Maximum Allowable Offer)
    mao = investor_offer - assignment_fee

    # Profit margins
    total_investor_cost = investor_offer + repairs
    investor_profit = arv - total_investor_cost
    investor_roi = (investor_profit / total_investor_cost) * 100 if total_investor_cost > 0 else 0

    print(f"""
ARV (After Repair Value):          ${arv:,.2f}
Investor Max ({arv_percentage*100:.0f}% of ARV):      ${investor_max:,.2f}
Minus Repairs:                     -${repairs:,.2f}
                                   ---------------
MAX INVESTOR PAYS:                 ${investor_offer:,.2f}

Minus Your Assignment Fee:         -${assignment_fee:,.2f}
                                   ---------------
YOUR MAO (Max Offer to Seller):    ${mao:,.2f}
""")

    print("=" * 60)
    print("          PROFIT BREAKDOWN")
    print("=" * 60)
    print(f"""
YOUR PROFIT (Assignment Fee):      ${assignment_fee:,.2f}

INVESTOR NUMBERS:
  Purchase Price:                  ${investor_offer:,.2f}
  Rehab Costs:                     ${repairs:,.2f}
  Total Investment:                ${total_investor_cost:,.2f}
  ARV (Sale Price):                ${arv:,.2f}
  Gross Profit:                    ${investor_profit:,.2f}
  ROI:                             {investor_roi:.1f}%
""")

    # Deal Rating
    print("=" * 60)
    print("          DEAL RATING")
    print("=" * 60)

    if investor_roi >= 20 and assignment_fee >= 5000:
        rating = "STRONG DEAL"
        notes = "Good margins for both you and investor"
    elif investor_roi >= 15 and assignment_fee >= 3000:
        rating = "DECENT DEAL"
        notes = "Acceptable margins, may need negotiation"
    elif investor_roi >= 10:
        rating = "THIN DEAL"
        notes = "Margins are tight, experienced investors only"
    else:
        rating = "PASS"
        notes = "Not enough margin, renegotiate or walk away"

    print(f"""
Rating: {rating}
Notes: {notes}
""")

    # Offer Strategy
    print("=" * 60)
    print("          OFFER STRATEGY")
    print("=" * 60)

    # Calculate offer range
    low_offer = mao * 0.85  # Start 15% below MAO

    print(f"""
Start negotiation at:              ${low_offer:,.2f}
Your MAO (walk-away point):        ${mao:,.2f}

NEGOTIATION TIPS:
1. Start at ${low_offer:,.2f} and work up
2. Never exceed ${mao:,.2f}
3. If seller won't budge, reduce your fee or walk away
4. Always justify your offer with repair estimates
""")

    return {
        'address': address,
        'arv': arv,
        'repairs': repairs,
        'mao': mao,
        'assignment_fee': assignment_fee,
        'investor_offer': investor_offer,
        'rating': rating
    }


def quick_mao():
    """Quick MAO calculator"""
    print("\n--- QUICK MAO CALCULATOR ---\n")
    arv = float(input("ARV: $"))
    repairs = float(input("Repairs: $"))
    fee = float(input("Your fee: $"))

    mao = (arv * 0.70) - repairs - fee
    print(f"\nYour MAO: ${mao:,.2f}")
    return mao


def comp_analyzer():
    """Analyze comps to determine ARV"""
    print("\n--- COMP ANALYZER ---\n")
    print("Enter recent comparable sales (enter 0 to finish):\n")

    comps = []
    i = 1
    while True:
        price = input(f"Comp {i} sale price (0 to finish): $")
        if price == "0" or price == "":
            break
        comps.append(float(price))
        i += 1

    if comps:
        avg = sum(comps) / len(comps)
        print(f"\nNumber of comps: {len(comps)}")
        print(f"Average sale price: ${avg:,.2f}")
        print(f"Range: ${min(comps):,.2f} - ${max(comps):,.2f}")
        print(f"\nSuggested ARV: ${avg:,.2f}")
        return avg
    return 0


def main():
    """Main menu"""
    while True:
        print("\n" + "=" * 60)
        print("       WHOLESALE DEAL ANALYZER - MAIN MENU")
        print("=" * 60)
        print("""
1. Full Deal Analysis
2. Quick MAO Calculator
3. Comp Analyzer (Calculate ARV)
4. Exit
""")
        choice = input("Select option (1-4): ")

        if choice == "1":
            analyze_deal()
        elif choice == "2":
            quick_mao()
        elif choice == "3":
            comp_analyzer()
        elif choice == "4":
            print("\nGood luck with your deals!\n")
            break
        else:
            print("Invalid option, try again")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
