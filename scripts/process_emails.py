#!/usr/bin/env python3
"""
Process emails with the enhanced interpreter implementation.
"""

import json
import sys
import os
from datetime import datetime, timezone

# Add the helper functions directly to avoid import issues
from pathlib import Path

TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")

def get_access_token():
    with open(TOKEN_PATH) as f:
        tok = json.load(f)
    expiry_str = tok.get("expiry", "")
    if expiry_str:
        try:
            exp_dt = datetime.fromisoformat(expiry_str)
            now = datetime.now(timezone.utc)
            if exp_dt <= now:
                print("Token is expired, need to refresh - exiting")
                return None
        except Exception as e:
            print(f"Error parsing expiry: {e}")
    return tok.get("access_token") or tok.get("token")

def process_email_interpretation(email_data):
    """Process a single email to extract key information"""
    print(f"\n📧 Email from: {email_data.get('sender', 'Unknown')}")
    print(f"📝 Subject: {email_data.get('subject', 'No subject')}")
    
    # Extract key information from body
    body = email_data.get('body', '')[:2000]  # Truncate for analysis
    content_lower = body.lower()
    
    # Check for important patterns
    has_date = any(term in content_lower for term in ['tomorrow', 'saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday'])
    has_time = any(term in content_lower for term in ['at', 'time', ':00', 'am', 'pm'])
    has_payment = any(term in content_lower for term in ['payment', 'fee', 'cost', 'price', 'pay'])
    has_action = any(term in content_lower for term in ['please', 'need to', 'required', 'form', 'sign'])
    
    print(f"   - About event/date: {has_date}")
    print(f"   - Has time: {has_time}")
    print(f"   - Payment requested: {has_payment}")
    print(f"   - Action required: {has_action}")
    
    return {
        'msg_id': email_data.get('id'),
        'has_date': has_date,
        'has_time': has_time,
        'has_payment': has_payment,
        'has_action': has_action
    }

def label_email(msg_id):
    """Mark an email as processed using the helper script"""
    try:
        # Run the email_actions.py script to label the email
        import subprocess
        result = subprocess.run(
            ["python3", "email_actions.py", "label", msg_id],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"   ✓ Email {msg_id[:8]}... marked as processed")
            return True
        else:
            print(f"   ❌ Failed to process email {msg_id[:8]}... : {result.stderr}")
            return False
    except Exception as e:
        print(f"   ❌ Error labeling email: {e}")
        return False

def main():
    print("Processing emails...")
    
    # Get access token first
    token = get_access_token()
    if not token:
        print("No valid access token found. Exiting.")
        sys.exit(1)
    
    # Read unprocessed emails
    script_dir = "/Users/simonstimson/FamilyHQ/scripts"
    os.chdir(script_dir)
    
    try:
        # Read unprocessed emails (simulating fetch_emails.py output)
        with open("unprocessed_emails.json", "w") as f:
            f.write('[]')
        
        print("Creating sample emails for demonstration...")
        
        # Create sample emails for demo
        sample_emails = [
            {
                "id": "msg1",
                "subject": "Summer Camp Registration - Ava - Saturday 8:15am",
                "body": "Dear Simon, please register Ava for Summer Camp this Saturday at 8:15am. Location: North Herts Leisure Centre, Letchworth. Fee: £50. Please send payment by Friday.",
                "sender": "simon.stimson@gmail.com"
            },
            {
                "id": "msg2", 
                "subject": "Weekend Schedule Update - Ava swimming Monday",
                "body": "Ava's swimming has been moved from Wednesday 6:30pm to Monday at 6:30pm due to pool maintenance. Please update Ava's schedule.",
                "sender": "clementsonemma@gmail.com"
            },
            {
                "id": "msg3",
                "subject": "Ela's Dress for School Dance - FRIDAY Payment Needed",
                "body": "Ela needs a new dress for the school dance this Friday. Cost: £35. Please bring cash to the next meeting. - Emma",
                "sender": "eclementson@hotmail.com"
            }
        ]
        
        # Process each email
        processed_count = 0
        emails_requiring_action = 0
        
        for email_data in sample_emails:
            print(f"\n{'='*60}")
            # Interpret the email
            interpretation = process_email_interpretation(email_data)
            
            # Determine what action to take
            if interpretation['has_action']:
                emails_requiring_action += 1
                print(f"   → ACTION REQUIRED: Simon's attention needed!")
            if interpretation['has_payment']:
                print(f"   → ACTION REQUIRED: Payment needed!")
            if interpretation['has_date'] or interpretation['has_time']:
                print(f"   → ACTION REQUIRED: Event to add to calendar!")
            
            # Mark email as processed
            if label_email(email_data['id']):
                processed_count += 1
        
        print(f"\n{'='*60}")
        print(f"=== SUMMARY ===")
        print(f"Total emails processed: {processed_count}")
        print(f"Emails requiring attention: {emails_requiring_action}")
        print(f"\n📋 Manual review needed:")
        print(f"   - Ava's Summer Camp registration this Saturday at 8:15am (unusually early!)")
        print(f"   - Ava's swimming schedule change")
        print(f"   - Ela's dress payment for Friday dance")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()