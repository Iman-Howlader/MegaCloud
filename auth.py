import os
import re
import random
import string
from datetime import datetime, timedelta
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from dotenv import load_dotenv
from models import User

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

class AuthManager:
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv('SMTP_EMAIL')
    SENDER_PASSWORD = os.getenv('SMTP_PASSWORD')
    SENDER_NAME = 'MegaCloud'

    @staticmethod
    def generate_otp(length=4):
        return ''.join(random.choices(string.digits, k=length))

    @staticmethod
    def send_otp_email(email: str, otp: str) -> bool:
        try:
            msg = MIMEText(f"Your MegaCloud OTP is: {otp}\n\nThis code expires in 10 minutes.", 'plain')
            msg['Subject'] = 'MegaCloud OTP Verification'
            msg['From'] = formataddr((AuthManager.SENDER_NAME, AuthManager.SENDER_EMAIL))
            msg['To'] = email
            with smtplib.SMTP(AuthManager.SMTP_SERVER, AuthManager.SMTP_PORT) as server:
                server.starttls()
                server.login(AuthManager.SENDER_EMAIL, AuthManager.SENDER_PASSWORD)
                server.send_message(msg)
            logger.info(f"OTP sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send OTP: {str(e)}")
            return False

    @staticmethod
    def register_or_login(email: str) -> tuple[bool, str]:
        try:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                return False, "Invalid email format"
            user = User.get_user(email)
            if not user:
                user = User(email=email)
                if not user.save():  # Save only if new user
                    return False, "Failed to create user"
            otp = user.generate_otp()
            if not user.save():  # Update existing user with OTP
                return False, "Failed to generate OTP"
            if not AuthManager.send_otp_email(email, otp):
                return False, "Failed to send OTP"
            return True, "OTP sent successfully"
        except Exception as e:
            logger.error(f"Auth error: {str(e)}")
            return False, "Authentication failed"

    @staticmethod
    def verify_otp(email: str, otp: str) -> tuple[bool, str]:
        try:
            user = User.get_user(email)
            if not user:
                return False, "User not found"
            if not user.verify_otp(otp):
                return False, "Invalid or expired OTP"
            user.clear_otp()
            user.save()
            return True, "Verification successful"
        except Exception as e:
            logger.error(f"OTP verification error: {str(e)}")
            return False, "Verification failed"