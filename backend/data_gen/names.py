"""Curated Pakistani name/business/item lists (Faker's en_PK locale uses US addresses)."""

MALE_FIRST = [
    "Muhammad", "Ahmed", "Ali", "Usman", "Bilal", "Hamza", "Imran", "Kashif", "Faisal", "Asad",
    "Zeeshan", "Waqas", "Adnan", "Shahid", "Tariq", "Naveed", "Rizwan", "Sajid", "Kamran", "Arslan",
    "Haris", "Junaid", "Saad", "Fahad", "Irfan", "Nadeem", "Aamir", "Yasir", "Salman", "Shoaib",
    "Danish", "Owais", "Umer", "Talha", "Abdullah", "Rehan", "Atif", "Jawad", "Mohsin", "Noman",
]
FEMALE_FIRST = [
    "Ayesha", "Fatima", "Sana", "Hira", "Maryam", "Zainab", "Amna", "Rabia", "Sadia", "Nida",
    "Uswa", "Mehwish", "Saba", "Kiran", "Iqra", "Areeba", "Mahnoor", "Sidra", "Bushra", "Farah",
]
LAST = [
    "Khan", "Malik", "Butt", "Chaudhry", "Sheikh", "Qureshi", "Rana", "Mirza", "Siddiqui", "Hashmi",
    "Awan", "Gill", "Raza", "Iqbal", "Javed", "Aslam", "Akhtar", "Hussain", "Nawaz", "Ansari",
    "Bhatti", "Cheema", "Dar", "Gondal", "Rehman", "Saleem", "Shah", "Tahir", "Warraich", "Zaidi",
]

LAHORE_AREAS = [
    "Shah Alam Market", "Akbari Mandi", "Badami Bagh", "Gulberg III", "Model Town", "Johar Town",
    "Township", "Ichhra", "Samanabad", "Garden Town", "Faisal Town", "Wapda Town", "Kot Lakhpat",
    "Sundar Industrial Estate", "Quaid-e-Azam Industrial Estate", "Raiwind Road", "Multan Road",
    "Ferozepur Road", "Allama Iqbal Town", "Shadbagh", "Misri Shah", "Bilal Gunj", "Hall Road",
    "Urdu Bazaar", "Liberty Market", "DHA Phase 5", "Cantt", "Baghbanpura", "Mughalpura", "Shalimar Town",
]
STREET_KINDS = ["Shop", "Plot", "Office", "Godown", "Unit"]
HOUSE_KINDS = ["House", "Flat"]

BANKS = {
    "HBL": "HABB",
    "MCB": "MUCB",
    "Meezan": "MEZN",
    "UBL": "UNIL",
    "Allied": "ABPA",
}

VENDOR_FIRST = [
    "Al-Noor", "Madina", "Bismillah", "Al-Rehman", "Pak", "Punjab", "Lahore", "Al-Hamd", "Ittefaq",
    "Al-Fazal", "Crescent", "Shalimar", "Ravi", "Indus", "Mehran", "Al-Karim", "Sadiq", "Ghani",
    "Hamza", "Al-Makkah", "Zam Zam", "Data", "Al-Barkat", "Haji", "Royal", "Prime", "Star", "Noor",
    "Hilal", "Al-Huda", "Mughal", "Faisal", "Rehmat", "Al-Syed", "Usmania", "Afzal", "Taj", "Sitara",
]
VENDOR_KIND = {
    "dairy": ["Dairies", "Milk Supply", "Dairy Products"],
    "beverages": ["Beverages", "Drinks Distributors", "Cold Drinks"],
    "snacks": ["Foods", "Snacks", "Food Industries"],
    "cooking_oil": ["Oil Mills", "Ghee Mills", "Edible Oils"],
    "personal_care": ["Cosmetics", "Soap Works", "Personal Care"],
    "packaging": ["Packages", "Packaging Industries", "Cartons"],
    "logistics": ["Goods Transport", "Logistics", "Carriage Services"],
    "services": ["Security Services", "Cleaning Services", "Maintenance Works"],
    "staples": ["Rice Mills", "Flour Mills", "Pulses Traders", "Sugar Traders"],
}
SUFFIX = ["Traders", "& Co.", "Enterprises", "(Pvt) Ltd", "Corporation", "Sons", "Brothers"]

CUSTOMER_SEGMENTS = {
    "kiryana": ["General Store", "Kiryana Store", "Karyana Merchants", "Provision Store"],
    "superstore": ["Super Store", "Mart", "Cash & Carry", "Super Market"],
    "wholesaler": ["Wholesale Traders", "Distributors", "Wholesalers"],
    "pharmacy": ["Pharmacy", "Medical Store", "Chemists"],
}
CUSTOMER_FIRST = [
    "Khan", "Madni", "Bismillah", "Al-Fatah", "Hafeez", "Rehmat", "Karachi", "Lahore", "Al-Habib",
    "Siddique", "Ghauri", "Butt", "Al-Shifa", "Faisal", "Saleem", "Jalal", "Iqbal", "Rafiq",
    "Chaudhry", "Hassan", "Sultan", "Hyder", "Yasin", "Akram", "Haider", "Usmani", "Nadeem", "Al-Kausar",
]

# (name, unit, category, base price in rupees)
ITEMS = [
    ("Fresh Milk 1L Pack", "carton", "dairy", 3600), ("UHT Milk 250ml", "carton", "dairy", 2700),
    ("Yogurt 1kg", "carton", "dairy", 2400), ("Butter 200g", "carton", "dairy", 9800),
    ("Cheese Slices 200g", "carton", "dairy", 11500), ("Cream 200ml", "carton", "dairy", 4600),
    ("Lassi 300ml", "carton", "dairy", 2100), ("Flavoured Milk 225ml", "carton", "dairy", 2900),
    ("Desi Ghee 1kg", "carton", "dairy", 21000), ("Milk Powder 400g", "carton", "dairy", 16800),
    ("Cola 1.5L", "carton", "beverages", 1650), ("Cola 345ml", "crate", "beverages", 1100),
    ("Lemon Lime 1.5L", "carton", "beverages", 1650), ("Orange Drink 1L", "carton", "beverages", 1500),
    ("Mineral Water 1.5L", "carton", "beverages", 720), ("Mineral Water 500ml", "carton", "beverages", 640),
    ("Mango Juice 200ml", "carton", "beverages", 1440), ("Apple Juice 1L", "carton", "beverages", 2900),
    ("Energy Drink 250ml", "carton", "beverages", 5400), ("Tea Bags 100s", "carton", "beverages", 14400),
    ("Loose Tea 900g", "carton", "beverages", 19800), ("Instant Coffee 100g", "carton", "beverages", 18600),
    ("Rooh Afza 800ml", "carton", "beverages", 7800), ("Tang Orange 500g", "carton", "beverages", 9600),
    ("Potato Chips 50g", "carton", "snacks", 2400), ("Nimko Mix 200g", "carton", "snacks", 3600),
    ("Biscuits Family Pack", "carton", "snacks", 2880), ("Cream Biscuits", "carton", "snacks", 2160),
    ("Cake Slices", "carton", "snacks", 1920), ("Chocolate Bar 40g", "carton", "snacks", 4800),
    ("Candy Jar", "carton", "snacks", 3000), ("Corn Puffs 30g", "carton", "snacks", 1800),
    ("Salted Peanuts 100g", "carton", "snacks", 3300), ("Rusk 300g", "carton", "snacks", 2640),
    ("Noodles Masala 65g", "carton", "snacks", 2880), ("Ketchup 800g", "carton", "snacks", 4320),
    ("Mayonnaise 1L", "carton", "snacks", 7200), ("Jam 440g", "carton", "snacks", 5280),
    ("Cooking Oil 5L Tin", "tin", "cooking_oil", 2950), ("Cooking Oil 1L Pouch", "carton", "cooking_oil", 6900),
    ("Banaspati Ghee 1kg", "carton", "cooking_oil", 6600), ("Banaspati Ghee 5kg Tin", "tin", "cooking_oil", 2750),
    ("Canola Oil 3L", "carton", "cooking_oil", 10800), ("Olive Oil 500ml", "carton", "cooking_oil", 21600),
    ("Corn Oil 1L", "carton", "cooking_oil", 8400), ("Sunflower Oil 5L", "tin", "cooking_oil", 3150),
    ("Bath Soap 100g", "carton", "personal_care", 6480), ("Laundry Soap Bar", "carton", "personal_care", 3600),
    ("Detergent Powder 1kg", "carton", "personal_care", 5400), ("Detergent Powder 500g", "carton", "personal_care", 5760),
    ("Shampoo 185ml", "carton", "personal_care", 9360), ("Shampoo Sachet", "carton", "personal_care", 2400),
    ("Toothpaste 100g", "carton", "personal_care", 7920), ("Toothbrush", "carton", "personal_care", 3600),
    ("Dishwash Bar", "carton", "personal_care", 3120), ("Dishwash Liquid 500ml", "carton", "personal_care", 5400),
    ("Hand Wash 250ml", "carton", "personal_care", 6000), ("Floor Cleaner 1L", "carton", "personal_care", 6480),
    ("Toilet Cleaner 500ml", "carton", "personal_care", 5280), ("Tissue Box", "carton", "personal_care", 4800),
    ("Face Cream 50g", "carton", "personal_care", 10800), ("Hair Oil 200ml", "carton", "personal_care", 8640),
    ("Shaving Cream", "carton", "personal_care", 7200), ("Razor Pack", "carton", "personal_care", 6000),
    ("Baby Diapers Medium", "pack", "personal_care", 2600), ("Sanitary Pads", "carton", "personal_care", 6240),
    ("Corrugated Carton 12x10", "bundle", "packaging", 4200), ("Corrugated Carton 18x12", "bundle", "packaging", 6300),
    ("Shrink Wrap Roll", "roll", "packaging", 5200), ("Packing Tape 2in", "carton", "packaging", 4320),
    ("Plastic Crate", "piece", "packaging", 1150), ("Wooden Pallet", "piece", "packaging", 3800),
    ("Poly Bags 10kg", "bundle", "packaging", 2100), ("Labels Roll", "roll", "packaging", 950),
    ("Stretch Film 18in", "roll", "packaging", 2650), ("Jute Bags", "bundle", "packaging", 3400),
    ("Basmati Rice 25kg", "bag", "staples", 8750), ("Sella Rice 25kg", "bag", "staples", 7600),
    ("Wheat Flour 20kg", "bag", "staples", 2300), ("Fine Atta 10kg", "bag", "staples", 1250),
    ("Sugar 50kg", "bag", "staples", 7250), ("Daal Chana 25kg", "bag", "staples", 6500),
    ("Daal Masoor 25kg", "bag", "staples", 7500), ("Daal Moong 25kg", "bag", "staples", 7000),
    ("White Chickpeas 25kg", "bag", "staples", 7750), ("Red Chilli Powder 1kg", "carton", "staples", 14400),
    ("Turmeric Powder 1kg", "carton", "staples", 10800), ("Salt 800g", "carton", "staples", 1440),
    ("Biryani Masala 50g", "carton", "staples", 6720), ("Garam Masala 100g", "carton", "staples", 8640),
    ("Vermicelli 150g", "carton", "staples", 2880), ("Custard Powder 300g", "carton", "staples", 5760),
    ("Corn Flour 300g", "carton", "staples", 3240), ("Baking Powder 100g", "carton", "staples", 2400),
    ("Gram Flour 1kg", "carton", "staples", 3960), ("Brown Sugar 1kg", "carton", "staples", 3840),
    ("Freight Lahore Local", "trip", "logistics", 6500), ("Freight Lahore-Faisalabad", "trip", "logistics", 28000),
    ("Freight Lahore-Gujranwala", "trip", "logistics", 18000), ("Freight Lahore-Sialkot", "trip", "logistics", 24000),
    ("Freight Lahore-Multan", "trip", "logistics", 52000), ("Freight Lahore-Islamabad", "trip", "logistics", 62000),
    ("Loading/Unloading Labour", "day", "logistics", 4500), ("Container Shifting", "trip", "logistics", 15000),
    ("Mazda Truck Rental", "day", "logistics", 9500), ("Shehzore Rental", "day", "logistics", 6000),
    ("Security Guard Monthly", "guard", "services", 38000), ("Night Watchman Monthly", "guard", "services", 32000),
    ("Office Cleaning Monthly", "month", "services", 45000), ("Warehouse Fumigation", "visit", "services", 28000),
    ("Generator Maintenance", "visit", "services", 22000), ("Forklift Service", "visit", "services", 18500),
    ("AC Servicing", "unit", "services", 3500), ("Electrical Repair Works", "job", "services", 12500),
    ("CCTV Maintenance", "visit", "services", 9500), ("Plumbing Works", "job", "services", 7500),
    ("Cold Room Repair", "job", "services", 42000), ("Racking Installation", "job", "services", 65000),
    ("Water Tanker", "trip", "services", 4500), ("Pest Control", "visit", "services", 8000),
    ("Diesel for Generator", "litre", "services", 285), ("Printer Toner", "piece", "services", 8500),
    ("Stationery Pack", "pack", "services", 2600), ("Uniforms Staff", "set", "services", 3800),
    ("Petrol Vouchers", "voucher", "logistics", 5000), ("Tyre Replacement", "piece", "logistics", 38000),
    ("Vehicle Service", "job", "logistics", 16500), ("Toll Tax Reimbursement", "trip", "logistics", 1200),
    ("Gas Cylinder 45kg", "cylinder", "services", 14500), ("LED Tube Lights", "carton", "services", 9600),
    ("Paint & Repair", "job", "services", 35000), ("Glass Repair", "job", "services", 6500),
    ("Weighing Scale Calibration", "visit", "services", 5500), ("Fire Extinguisher Refill", "piece", "services", 3200),
    ("Pallet Truck", "piece", "packaging", 78000), ("Plastic Pallet", "piece", "packaging", 6800),
    ("Bubble Wrap Roll", "roll", "packaging", 3900), ("Carton Sealing Machine Service", "visit", "packaging", 8000),
]

VAGUE_ITEMS = [
    "Consultancy services", "Misc. services", "Professional services", "Market survey services",
    "Supply of goods", "Advisory charges", "Coordination services", "Service charges",
]

DEPARTMENTS = [
    ("Sales", ["Sales Officer", "Order Booker", "Area Sales Manager"]),
    ("Warehouse", ["Store Keeper", "Picker", "Warehouse Supervisor"]),
    ("Purchase", ["Purchase Officer", "Procurement Executive", "Purchase Manager"]),
    ("Accounts", ["Accountant", "Accounts Assistant", "Finance Manager"]),
    ("Delivery", ["Driver", "Delivery Helper", "Fleet Supervisor"]),
    ("Admin", ["Admin Officer", "Office Boy", "HR Executive"]),
]
