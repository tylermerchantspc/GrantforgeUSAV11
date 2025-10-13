import pandas as pd
from datetime import datetime

# Input and output file names
INPUT_FILE = "cache_v1.csv"
OUTPUT_FILE = "safe_cache_v1.csv"

# Load the CSV file
df = pd.read_csv(INPUT_FILE)

# Convert 'Deadline' to datetime, skip bad or blank values
df['Deadline'] = pd.to_datetime(df['Deadline'], errors='coerce')

# Calculate how many days remain
today = datetime.utcnow()
df['Days Left'] = (df['Deadline'] - today).dt.days

# Filter for grants with 60+ days remaining
safe_df = df[df['Days Left'] >= 60]

# Save the results
safe_df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ Safe grants saved to {OUTPUT_FILE} ({len(safe_df)} records with 60+ days left).")