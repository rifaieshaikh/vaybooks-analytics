"""Vay wholesale industry pack — expense account map seed only.

Not imported by formula modules as a hard dependency for other pilots.
Default seed for org expense categories when none are configured.
"""

PACK_ID = "vay_wholesale"
PACK_LABEL = "Vay wholesale (default seed)"

# Account Name values historically used at Vay → expense category.
EXPENSE_ACCOUNT_MAP = {
    "Travel Expenses": [
        "RAHUL_EXPENSE", "SAKARIYA_EXPENCE", "FUEL_EXPENSE", "VEHICLE EXPENSE", "Vehicle maintenance",
    ],
    "Courier": ["COURIER CHARGE", "EASY_PARCEL", "NEST_DP", "DREAMS_DP"],
    "Office Expenses": [
        "OFFICE_STATIONARY_EXPENCE", "OFFICE_ELECTRICITY_EXPENCE", "OFFICE_FOOD_EXPENCE",
        "OTHER_OFFICE_MISE_EXPENCE", "Electricity and water charges", "Electrical Fittings",
        "RENT SHOP PAYABLE", "Donation and charity", "MARKETING_EXPENSE", "AMAL_TRADERS",
        "ZAINU EXPENCE", "JIJIETTAN_EXPENCE", "Carriage inward",
    ],
    "Salary": [
        "SAKARIYA _SALARY", "SAKARIYA_SALARY", "JIJIETTAN_SALARY", "RIFAIE _SALARY", "RIFAIE_SALARY",
        "ISMAIL_SALARY", "ABDULLAH KOYA_SALARY", "RAHUL_SALARY", "ZAINU_SALARY",
        "ABHILASH_SALARY",
    ],
    "Compliance Expenses": ["SAREENA K_SALARY"],
    "Investment Returns": [
        "AYISHA_YASMIN_INVESTMENT", "RASMILA_INVESTMENT", "YASIRA_BEEVI_INVESTMENT",
        "ISMAIL CARE OF_NASEEB INVESTMENT", "ISMAIL CARE OF_MIDHLAJ INVESTMENT",
        "ISMAIL CARE OF_JIBNA INVESTMENT", "RIFAIE_CARE OF_KADHEEJA INVESTMENT",
    ],
    "Purchase": [
        "RAHMA ASSOCIATES_VENDOR", "HINDPRAKASH INDUSTRIES LIMITED",
        "IC SOLUTIONS",
    ],
    "Bank Inward": ["HDFC BANK", "FEDERAL BANK-3698"],
    "RD": ["COMPANY RD", "COMPANY RD2", "COMPANY RD3"],
}
