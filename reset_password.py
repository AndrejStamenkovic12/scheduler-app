#!/usr/bin/env python3
"""
Password reset script for the appointment scheduler
"""

import hashlib
import json
import os

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def reset_password(username, new_password):
    """Reset password for a user"""
    users_file = "users.json"
    
    if not os.path.exists(users_file):
        print(f"Error: {users_file} not found")
        return False
    
    # Load users
    with open(users_file, 'r') as f:
        users = json.load(f)
    
    # Find user
    user_found = False
    for user in users:
        if user['username'] == username:
            user['password'] = hash_password(new_password)
            user_found = True
            print(f"Password reset for user '{username}'")
            break
    
    if not user_found:
        print(f"User '{username}' not found")
        return False
    
    # Save users
    with open(users_file, 'w') as f:
        json.dump(users, f, indent=2)
    
    print(f"Password successfully reset for user '{username}'")
    return True

if __name__ == "__main__":
    # Reset password for andrej user
    username = "andrej"
    new_password = "password123"  # Change this to your desired password
    
    print(f"Resetting password for user: {username}")
    print(f"New password will be: {new_password}")
    
    confirm = input("Do you want to proceed? (y/n): ")
    if confirm.lower() == 'y':
        reset_password(username, new_password)
    else:
        print("Password reset cancelled")
