#!/usr/bin/env python3
"""
BTU OBS Exam Result Notification Bot
Main entry point - Periodically checks for new grades and sends Telegram notifications.
"""

import json
import time
import signal
import sys
import argparse
from datetime import datetime
from pathlib import Path

import schedule

import config
from obs_scraper import OBSSession, get_new_grades
from telegram_bot import (
    send_multiple_grades_notification,
    send_startup_message,
    send_error_notification,
    send_message,
)


# Global flag for graceful shutdown
running = True


def load_cache() -> list[dict]:
    """Load cached grades from file."""
    cache_path = Path(config.CACHE_FILE)
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[!] Error loading cache: {e}")
    return []


def save_cache(grades: list[dict]) -> None:
    """Save grades to cache file."""
    try:
        with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(grades, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"[!] Error saving cache: {e}")


def check_for_new_grades() -> None:
    """Main check function - fetches grades and sends notifications for new ones."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new grades...")
    
    try:
        # Load cached grades
        cached_grades = load_cache()
        
        # Fetch current grades
        obs = OBSSession()
        current_grades = obs.fetch_grades()
        obs.close()
        
        if not current_grades:
            print("[*] No grades found or error fetching grades")
            return
        
        # Find new grades
        new_grades = get_new_grades(cached_grades, current_grades)
        
        if new_grades:
            print(f"[+] Found {len(new_grades)} new grade(s)!")
            
            # Send notification
            if send_multiple_grades_notification(new_grades):
                print("[+] Notification sent successfully")
            else:
                print("[!] Failed to send notification")
            
            # Update cache with all current grades
            save_cache(current_grades)
        else:
            print("[*] No new grades")
            
    except Exception as e:
        error_msg = f"Error during grade check: {e}"
        print(f"[!] {error_msg}")
        send_error_notification(error_msg)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global running
    print("\n[*] Shutdown signal received, stopping...")
    running = False


def run_test_mode():
    """Run in test mode - single check without loop."""
    print("=" * 50)
    print("BTU OBS Notification Bot - TEST MODE")
    print("=" * 50)
    
    # Validate config
    try:
        config.validate_config()
        print("[+] Configuration validated successfully")
    except ValueError as e:
        print(f"[!] Configuration error: {e}")
        sys.exit(1)
    
    # Test Telegram connection
    print("\n[*] Testing Telegram connection...")
    if send_message("🔧 Test mesajı - OBS Bildirim Botu çalışıyor!"):
        print("[+] Telegram test message sent successfully")
    else:
        print("[!] Failed to send Telegram test message")
        sys.exit(1)
    
    # Test OBS login
    print("\n[*] Testing OBS login...")
    obs = OBSSession()
    if obs.login():
        print("[+] OBS login successful")
        
        # Try to fetch grades
        print("\n[*] Fetching grades...")
        grades = obs.fetch_grades()
        if grades:
            print(f"[+] Found {len(grades)} grade(s):")
            for g in grades[:5]:  # Show first 5
                print(f"    - {g['course_code']}: {g['course_name']} = {g['grade']}")
            if len(grades) > 5:
                print(f"    ... and {len(grades) - 5} more")
        else:
            print("[*] No grades found (this is normal if no results announced)")
    else:
        print("[!] OBS login failed")
    
    obs.close()
    print("\n[+] Test completed!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="BTU OBS Exam Result Notification Bot")
    parser.add_argument("--test", action="store_true", help="Run in test mode (single check)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        print(f"[!] Configuration error: {e}")
        print("\nPlease set the following environment variables:")
        print("  - OBS_USERNAME: Your OBS username")
        print("  - OBS_PASSWORD: Your OBS password")
        print("  - TELEGRAM_BOT_TOKEN: Your Telegram bot token")
        print("  - TELEGRAM_CHAT_ID: Your Telegram chat ID")
        sys.exit(1)
    
    if args.test:
        run_test_mode()
        return
    
    if args.once:
        check_for_new_grades()
        return
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 50)
    print("BTU OBS Exam Result Notification Bot")
    print("=" * 50)
    print(f"Check interval: {config.CHECK_INTERVAL} minutes")
    print("Press Ctrl+C to stop\n")
    
    # Send startup message
    send_startup_message()
    
    # Run initial check
    check_for_new_grades()
    
    # Schedule periodic checks
    schedule.every(config.CHECK_INTERVAL).minutes.do(check_for_new_grades)
    
    # Main loop
    while running:
        schedule.run_pending()
        time.sleep(1)
    
    print("[*] Bot stopped")


if __name__ == "__main__":
    main()
