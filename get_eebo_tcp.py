# Download all Github-archived EEBO-TCP xml files from their associated repositories on Github
# Files were created "by converting TCP files to TEI P5 using tcp2tei.xsl,TEI @ Oxford."

# Running this script requires two preparatory steps. Either could be eliminated with a simple modification
# 1. Creating a destination folder called tcp (all lowercase) that is placed in the same folder as this script
# 2. Downloading "TCP.csv" (all caps filename) from https://github.com/textcreationpartnership/Texts and placing it in the same folder as this script
import requests
import pandas as pd
import os

# Create the 'tcp' directory if it doesn't already exist
if not os.path.exists('tcp'):
    os.makedirs('tcp')

# comment these lines out if you have the file already
print("Downloading TCP.csv...")
r = requests.get("https://raw.githubusercontent.com/textcreationpartnership/Texts/master/TCP.csv")
r.raise_for_status() # Make sure the download was successful

# Specify UTF-8 encoding to prevent UnicodeEncodeError
# Use 'w' (write) mode to ensure you get a fresh file each time. 'a' (append) could lead to a malformed CSV.
with open("TCP.csv", "w", encoding="utf-8") as f:
    f.write(r.text)

print("Reading CSV file...")
# Specify dtype=str to prevent DtypeWarning and ensure all IDs are read as strings
df = pd.read_csv("TCP.csv", dtype=str)

# The .dropna() is added to handle any potentially empty rows in the CSV
ids = list(df['TCP'].dropna())
total_files = len(ids)
print(f"Found {total_files} files to download.")

for count, i in enumerate(ids):
    # Construct the URL
    x = f"https://raw.githubusercontent.com/textcreationpartnership/{i}/master/{i}.xml"
    # Define the output file path
    output_path = os.path.join("tcp", f"{i}.xml")

    # Optional: Skip download if file already exists
    if os.path.exists(output_path):
        print(f"({count+1}/{total_files}) Skipping {i}, file already exists.")
        continue

    print(f"({count+1}/{total_files}) Downloading {i}...")
    try:
        xml_file = requests.get(x)
        # This will raise an error for bad responses (like 404 Not Found)
        xml_file.raise_for_status()
        
        # requests will guess the encoding, but we can be explicit
        xml_file.encoding = 'utf-8'
        xml_txt = xml_file.text

        # Use the 'with' statement which handles closing the file automatically
        with open(output_path, "w", encoding="utf-8") as myfile:
            myfile.write(xml_txt)

    except requests.exceptions.RequestException as e:
        # It's good practice to print errors to see what's failing
        print(f"--- Failed to download {x}: {e}")
    except Exception as e:
        print(f"--- An unexpected error occurred for {i}: {e}")

print("Script finished.")