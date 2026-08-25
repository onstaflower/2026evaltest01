import os
import sys
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

spreadsheet_id = "1b4jFv5sLf9mZt3hPmZH5fnnw6klLSpwPhN4zZVne6dM"

key_path = "evaltest01.json"
if not os.path.exists(key_path):
    key_path = "evaltest01/evaltest01.json"

print(f"Testing key path: {key_path}, exists: {os.path.exists(key_path)}")

try:
    creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    print(f"Service account email: {creds.service_account_email}")
    
    print(f"Attempting to open spreadsheet ID: {spreadsheet_id}")
    sh = client.open_by_key(spreadsheet_id)
    print(f"SUCCESS! Spreadsheet title: {sh.title}")
    
    worksheets = sh.worksheets()
    print(f"Worksheets: {[ws.title for ws in worksheets]}")
except Exception as e:
    print(f"FAILED with error: {type(e).__name__}: {str(e)}")
