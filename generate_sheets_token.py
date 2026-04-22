#!/usr/bin/env python3
"""
Run this once locally to generate a google_token.pickle with Sheets + Drive scopes.
Then encode it and update your GOOGLE_TOKEN_PICKLE GitHub secret.
"""
import pickle
import base64
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = None

if os.path.exists("sheets_token.pickle"):
    with open("sheets_token.pickle", "rb") as f:
        creds = pickle.load(f)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        # You need a credentials.json from Google Cloud Console
        # APIs & Services -> Credentials -> OAuth 2.0 Client -> Download JSON
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)

    with open("sheets_token.pickle", "wb") as f:
        pickle.dump(creds, f)

# Encode to base64 for GitHub secret
encoded = base64.b64encode(open("sheets_token.pickle", "rb").read()).decode()
print("\n✅ Copy this and update your GOOGLE_TOKEN_PICKLE secret in GitHub:\n")
print(encoded)
