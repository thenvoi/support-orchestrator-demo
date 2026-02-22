"""
Generate mock customers.xlsx for the support orchestrator demo.

Creates a realistic customer database with 18 rows including key records:
- sarah@acme.com (Pro plan, CSV Export included) — used in Branch A/B demos
- john@startup.io (Free plan, no CSV Export) — used in Branch C demo

Usage:
    python demo_data/generate_customers.py

Output:
    demo_data/customers.xlsx
"""

import os

import pandas as pd

# Resolve output path relative to this script.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_OUTPUT_PATH = os.path.join(_SCRIPT_DIR, "customers.xlsx")

CUSTOMERS = [
    {
        "email": "sarah@acme.com",
        "name": "Sarah Chen",
        "company": "Acme Corp",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "ACM-2847",
        "signup_date": "2025-06-15",
    },
    {
        "email": "john@startup.io",
        "name": "John Park",
        "company": "StartupIO",
        "plan": "Free",
        "status": "Active",
        "features": "Dashboard",
        "account_id": "SIO-1102",
        "signup_date": "2025-11-01",
    },
    {
        "email": "maria@bigcorp.com",
        "name": "Maria Gonzalez",
        "company": "BigCorp Industries",
        "plan": "Enterprise",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access, SSO, Audit Log",
        "account_id": "BCI-0501",
        "signup_date": "2024-09-20",
    },
    {
        "email": "alex@devshop.dev",
        "name": "Alex Kumar",
        "company": "DevShop",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "DSH-3391",
        "signup_date": "2025-03-10",
    },
    {
        "email": "lisa@oceanview.co",
        "name": "Lisa Wang",
        "company": "OceanView Analytics",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "OVA-4472",
        "signup_date": "2025-01-22",
    },
    {
        "email": "tom@freelance.me",
        "name": "Tom Nguyen",
        "company": "Freelance",
        "plan": "Free",
        "status": "Active",
        "features": "Dashboard",
        "account_id": "FRL-5583",
        "signup_date": "2025-12-05",
    },
    {
        "email": "emma@techstart.com",
        "name": "Emma Davis",
        "company": "TechStart Inc",
        "plan": "Pro",
        "status": "Churned",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "TSI-6604",
        "signup_date": "2024-11-15",
    },
    {
        "email": "raj@finserv.co",
        "name": "Raj Patel",
        "company": "FinServ Solutions",
        "plan": "Enterprise",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access, SSO, Audit Log",
        "account_id": "FSS-7715",
        "signup_date": "2024-06-01",
    },
    {
        "email": "chen@dataflow.ai",
        "name": "Wei Chen",
        "company": "DataFlow AI",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "DFA-8826",
        "signup_date": "2025-07-18",
    },
    {
        "email": "kate@nonprofit.org",
        "name": "Kate Miller",
        "company": "GreenEarth Foundation",
        "plan": "Free",
        "status": "Active",
        "features": "Dashboard",
        "account_id": "GEF-9937",
        "signup_date": "2025-10-30",
    },
    {
        "email": "dan@retailco.com",
        "name": "Dan Roberts",
        "company": "RetailCo",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "RCO-1048",
        "signup_date": "2025-04-12",
    },
    {
        "email": "yuki@mediahub.jp",
        "name": "Yuki Tanaka",
        "company": "MediaHub Japan",
        "plan": "Enterprise",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access, SSO, Audit Log",
        "account_id": "MHJ-1159",
        "signup_date": "2024-12-01",
    },
    {
        "email": "sam@cloudops.io",
        "name": "Sam Rivera",
        "company": "CloudOps",
        "plan": "Pro",
        "status": "Trial",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "COP-1260",
        "signup_date": "2026-01-28",
    },
    {
        "email": "nina@designlab.co",
        "name": "Nina Petrov",
        "company": "DesignLab",
        "plan": "Free",
        "status": "Active",
        "features": "Dashboard",
        "account_id": "DLB-1371",
        "signup_date": "2025-08-14",
    },
    {
        "email": "james@healthtech.com",
        "name": "James O'Brien",
        "company": "HealthTech Solutions",
        "plan": "Enterprise",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access, SSO, Audit Log",
        "account_id": "HTS-1482",
        "signup_date": "2024-03-15",
    },
    {
        "email": "priya@edtech.in",
        "name": "Priya Sharma",
        "company": "EduLearn India",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "ELI-1593",
        "signup_date": "2025-05-20",
    },
    {
        "email": "mike@buildfast.dev",
        "name": "Mike Thompson",
        "company": "BuildFast",
        "plan": "Free",
        "status": "Churned",
        "features": "Dashboard",
        "account_id": "BFS-1604",
        "signup_date": "2025-09-01",
    },
    {
        "email": "ana@logisticspro.com",
        "name": "Ana Moreno",
        "company": "LogisticsPro",
        "plan": "Pro",
        "status": "Active",
        "features": "Dashboard, CSV Export, API Access",
        "account_id": "LPR-1715",
        "signup_date": "2025-02-28",
    },
]


def main() -> None:
    df = pd.DataFrame(CUSTOMERS)
    df.to_excel(_OUTPUT_PATH, index=False, sheet_name="Customers")
    print(f"Created {_OUTPUT_PATH} with {len(df)} customer records.")
    print(f"\nKey test records:")
    print(f"  sarah@acme.com  — Pro plan, CSV Export included (Branch A/B)")
    print(f"  john@startup.io — Free plan, no CSV Export (Branch C)")


if __name__ == "__main__":
    main()
