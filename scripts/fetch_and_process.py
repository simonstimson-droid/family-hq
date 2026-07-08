#!/usr/bin/env python3
"""
Wrapper to fetch emails and process them in the background.
"""

import subprocess
import sys
import json
import os
import time

def process_email_interpretation(email_data):
    """Process a single email to extract key information"""
    print(f"\n📧 Email from: {email_data.get('sender', 'Unknown')}")
    print(f"📝 Subject: {email_data.get('subject', 'No subject')}")
    
    # Extract key information
    body = email_data.get('body', '')[:2000]  # Truncate for analysis
    
    # Check for important patterns
    content_lower = body.lower()
    
    # Check for event/info with dates
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

def main():
    print("Fetching emails...")
    
    # Change to the scripts directory
    script_dir = "/Users/simonstimson/FamilyHQ/scripts"
    os.chdir(script_dir)
    
    # Run fetch_emails.py
    try:
        result = subprocess.run(
            ["python3", "fetch_emails.py"], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0:
            # Try to parse the JSON output
            try:
                emails = json.loads(result.stdout)
                print(f"Successfully fetched emails: {len(emails)} found")
                
                if emails:
                    print(f"\n=== PROCESSING {len(emails)} EMAILS ===")
                    
                    # Process each email
                    processed_count = 0
                    for email_data in emails:
                        # Interpret the email
                        interpretation = process_email_interpretation(email_data)
                        
                        # For now, just label each email as processed
                        # In a full implementation, we would use email_actions.py label <msg_id>
                        # For now, print what action should be taken
                        if interpretation['has_action']:
                            print(f"   → RECOMMENDATION: Create reminder or action")
                        if interpretation['has_payment']:
                            print(f"   → RECOMMENDATION: Check payment section")
                        if interpretation['has_date'] or interpretation['has_time']:
                            print(f"   → RECOMMENDATION: Check calendar")
                        
                        print(f"   ✓ Would label as processed: {email_data.get('id', 'N/A')[:8]}...")
                        processed_count += 1
                    
                    print(f"\n=== SUMMARY ===")
                    print(f"Total emails processed: {processed_count}")
                    print(f"Emails requiring attention: {sum(1 for e in emails if process_email_interpretation(e)['has_action'] or process_email_interpretation(e)['has_payment'])}")
                    print("\nNote: This is a demonstration. Full integration with email_actions.py needed for complete processing.")
                    
                else:
                    print("No new emails to process")
                    
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
                print("Raw output:", result.stdout)
        else:
            print(f"Error running fetch_emails.py: {result.stderr}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()