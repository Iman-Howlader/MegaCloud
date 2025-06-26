import os
import random
import string
from datetime import datetime, timedelta
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from dotenv import load_dotenv
from models import User
from tenacity import retry, stop_after_attempt, wait_fixed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

class AuthManager:
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SENDER_EMAIL = os.getenv('SMTP_EMAIL', 'default@example.com')
    SENDER_PASSWORD = os.getenv('SMTP_PASSWORD', 'default_password')
    SENDER_NAME = os.getenv('SMTP_SENDER_NAME', 'MegaCloud')
    OTP_LENGTH = int(os.getenv('OTP_LENGTH', 4))

    @staticmethod
    def generate_otp(length=None):
        length = length or AuthManager.OTP_LENGTH
        return ''.join(random.choices(string.digits, k=length))

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
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
            logger.error(f"Failed to send OTP to {email}: {str(e)}")
            raise

    @staticmethod
    def verify_otp(email: str, otp: str) -> tuple[bool, str]:
        try:
            user = User.get_user_by_email(email)
            if not user:
                return False, "User not found"
                
            if not user.verify_otp(otp):
                return False, "Invalid or expired OTP"
                
            user.clear_otp()
            user.save()
            return True, "Verification successful"
        except Exception as e:
            logger.error(f"OTP verification error for {email}: {str(e)}")
            return False, "Verification failed"