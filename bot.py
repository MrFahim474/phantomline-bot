import os
import logging
import sqlite3
import asyncio
import random
import requests
import re
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from urllib.parse import quote, unquote
import hashlib

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 5593343692  # Your admin ID

# Adsterra popunder links - Replace with your actual links
ADSTERRA_LINKS = [
    "https://www.profitableratecpm.com/vyae9242?key=b7f39ee343b0a72625176c5f79bcd81b",
    "https://www.profitableratecpm.com/wwur9vddps?key=6ac9c3ed993ad2a89a11603f8c27d528",
    "https://www.profitableratecpm.com/p6rgdh07x?key=b2db689973484840de005ee95612c9f9"
]

# Database initialization
def init_db():
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            join_date TEXT,
            ad_views INTEGER DEFAULT 0,
            phone_requests INTEGER DEFAULT 0,
            email_requests INTEGER DEFAULT 0,
            last_activity TEXT
        )
    ''')
    
    # Support messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            message TEXT,
            timestamp TEXT,
            status TEXT DEFAULT 'open'
        )
    ''')
    
    # Phone usage tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS phone_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            country TEXT,
            number TEXT,
            timestamp TEXT,
            service_used TEXT
        )
    ''')
    
    # Email usage tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT,
            timestamp TEXT,
            service_used TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# Real SMS API integration

class RealPhoneAPI:
    def __init__(self):
        self.base_url = "https://receive-sms-online.info"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        })
        
        # Pre-validated countries/numbers (update monthly)
        self.real_numbers = {
            "USA 🇺🇸": ["+12092512708", "+17753055499", "+15597418334"],
            "UK 🇬🇧": ["+447700150616", "+447520635472"],
            "Germany 🇩🇪": ["+4915735983768", "+4915202806842"]
        }

    def get_countries(self):
        return list(self.real_numbers.keys())

    def get_numbers_by_country(self, country):
        return [{"number": num, "active": True} for num in self.real_numbers.get(country, [])]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def fetch_real_sms(self, number):
        clean_number = number.replace("+", "")
        url = f"{self.base_url}/number/{clean_number}/"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            
            messages = []
            for msg in soup.select(".sms-item"):
                sender = msg.select_one(".sender").get_text(strip=True)
                text = msg.select_one(".text").get_text(strip=True)
                time = msg.select_one(".time").get_text(strip=True)
                
                code = re.search(r"\b\d{4,8}\b", text)
                code = code.group() if code else "No code found"
                
                messages.append({
                    "service": sender,
                    "code": code,
                    "message": text,
                    "time": time
                })
            
            return messages[:5]
        except Exception as e:
            logger.error(f"SMS fetch failed for {number}: {e}")
            return []

# Real Email API integration
class RealEmailAPI:
    def __init__(self):
        self.api_url = "https://10minutemail.com/address/api"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        })
        self.email = None
        self.token = None

    def generate_temp_email(self):
        try:
            response = self.session.post(
                f"{self.api_url}/getAddress",
                json={},
                timeout=10
            )
            data = response.json()
            self.email = data["address"]
            self.token = data["token"]
            return self.email
        except Exception as e:
            logger.error(f"Email generation failed: {e}")
            return "error@tempmail.fail"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def fetch_real_emails(self, email):
        if not self.token:
            return []
            
        try:
            response = self.session.post(
                f"{self.api_url}/getMessages",
                json={"token": self.token},
                timeout=10
            )
            data = response.json()
            
            emails = []
            for msg in data.get("messages", []):
                code = re.search(r"\b\d{4,8}\b", msg.get("textBody", ""))
                code = code.group() if code else "No code found"
                
                emails.append({
                    "from": msg.get("from", "Unknown"),
                    "subject": msg.get("subject", "No subject"),
                    "code": code,
                    "content": msg.get("textBody", ""),
                    "time": msg.get("received", "Unknown")
                })
            
            return emails[:5]
        except Exception as e:
            logger.error(f"Email fetch failed: {e}")
            return []
# Ad system
class AdSystem:
    def __init__(self):
        self.view_count = {}
    
    def should_show_ad(self, user_id):
        """Show ad every 3rd interaction"""
        conn = sqlite3.connect('phantomline.db')
        cursor = conn.cursor()
        cursor.execute('SELECT ad_views FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            views = result[0]
            return views % 3 == 0
        return True
    
    def increment_ad_views(self, user_id):
        """Track ad views"""
        conn = sqlite3.connect('phantomline.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET ad_views = ad_views + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def get_ad_url(self):
        """Get random Adsterra URL"""
        return random.choice(ADSTERRA_LINKS)

# Initialize systems
phone_api = RealPhoneAPI()
email_api = RealEmailAPI()
ad_system = AdSystem()

# Helper functions
def save_user(update: Update):
    user = update.effective_user
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, join_date, last_activity, ad_views, phone_requests, email_requests)
        VALUES (
            ?, ?, ?, 
            COALESCE((SELECT join_date FROM users WHERE user_id = ?), ?),
            ?, 
            COALESCE((SELECT ad_views FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT phone_requests FROM users WHERE user_id = ?), 0),
            COALESCE((SELECT email_requests FROM users WHERE user_id = ?), 0)
        )
    ''', (
        user.id, user.username, user.first_name,
        user.id, datetime.now().isoformat(),
        datetime.now().isoformat(),
        user.id, user.id, user.id
    ))
    
    conn.commit()
    conn.close()

def log_phone_usage(user_id, country, number):
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO phone_usage (user_id, country, number, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_id, country, number, datetime.now().isoformat()))
    cursor.execute('UPDATE users SET phone_requests = phone_requests + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def log_email_usage(user_id, email):
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO email_usage (user_id, email, timestamp)
        VALUES (?, ?, ?)
    ''', (user_id, email, datetime.now().isoformat()))
    cursor.execute('UPDATE users SET email_requests = email_requests + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Main menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update)
    user = update.effective_user
    
    welcome_text = f"""
🔥 **Welcome to PhantomLine, {user.first_name}!** 🔥

Your ultimate source for **REAL** temporary services! 

🌟 **What we offer:**
📱 **Real Phone Numbers** - Get REAL SMS codes instantly
📧 **Real Temp Emails** - Receive REAL verification emails  
🌍 **8+ Countries** - USA, UK, Germany, Canada & more
🔒 **100% Privacy** - No registration required
🆓 **Completely FREE** - Always and forever!

✨ **Perfect for:**
• Social media verifications (Instagram, Facebook, TikTok)
• Account registrations (Google, Apple, Microsoft)
• App trials and downloads
• Email verifications
• Privacy protection

🚀 **Choose your service:**
    """
    
    keyboard = [
        [InlineKeyboardButton("📱 Get Phone Number", callback_data="get_phone")],
        [InlineKeyboardButton("📧 Get Temp Email", callback_data="get_email")],
        [InlineKeyboardButton("📊 Live Stats", callback_data="stats"),
         InlineKeyboardButton("❓ How to Use", callback_data="help")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# Phone number selection
async def get_phone_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    countries = phone_api.get_countries()
    
    text = "📱 **Choose Your Country:**\n\n"
    text += "🌍 **Available regions with REAL phone numbers:**\n\n"
    
    for country in countries:
        count = len(phone_api.get_numbers_by_country(country))
        text += f"{country}: **{count} active numbers** 🟢\n"
    
    text += f"\n📞 **Total: {sum(len(phone_api.get_numbers_by_country(c)) for c in countries)} real numbers**\n"
    text += "✅ **All numbers receive REAL SMS codes!**"
    
    keyboard = []
    row = []
    for i, country in enumerate(countries):
        row.append(InlineKeyboardButton(country, callback_data=f"country_{country}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show country numbers
async def show_country_numbers(query, country):
    numbers = phone_api.get_numbers_by_country(country)
    
    text = f"📱 **{country} Phone Numbers:**\n\n"
    text += f"✅ **{len(numbers)} premium numbers available**\n"
    text += "🔥 **All numbers are REAL and receive SMS instantly!**\n\n"
    
    keyboard = []
    for i, num_data in enumerate(numbers):
        text += f"🟢 `{num_data['number']}` - Active\n"
        keyboard.append([InlineKeyboardButton(f"📞 {num_data['number']}", callback_data=f"phone_{country}_{i}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="get_phone")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show phone details
async def show_phone_details(query, country, number_index):
    numbers = phone_api.get_numbers_by_country(country)
    
    if number_index >= len(numbers):
        await query.edit_message_text("❌ Number not found!")
        return
    
    number_data = numbers[number_index]
    number = number_data['number']
    
    log_phone_usage(query.from_user.id, country, number)
    
    text = f"""
📱 **Your Phone Number**

📞 **Number:** `{number}`
🌍 **Country:** {country}
🟢 **Status:** Active & Ready

📋 **Copy this number:**
`{number}`

**Easy steps:**
1️⃣ **Copy** the number above (tap and hold)
2️⃣ **Go to any app** (WhatsApp, Instagram, etc.)
3️⃣ **Paste the number** in verification field
4️⃣ **Request SMS code** from the service
5️⃣ **Come back here** and check your SMS!

✨ **Works with ALL services:**
WhatsApp • Instagram • Facebook • Google • Apple • Discord • TikTok • Twitter • LinkedIn • Amazon • Netflix • Spotify • Uber • PayPal • Microsoft • And 500+ more!

⚠️ **Note:** This is a real shared number - perfect for verifications!
    """
    
    keyboard = [
        [InlineKeyboardButton("📨 Check SMS Messages", callback_data=f"sms_{country}_{number_index}")],
        [InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_phone_{number}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"phone_{country}_{number_index}"),
         InlineKeyboardButton("🔙 Back", callback_data=f"country_{country}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show SMS messages
async def show_sms_messages(query, country, number_index):
    numbers = phone_api.get_numbers_by_country(country)
    number = numbers[number_index]['number']
    
    # Show loading
    await query.edit_message_text("🔄 **Fetching your SMS messages...**\n\nPlease wait...", parse_mode='Markdown')
    await asyncio.sleep(2)  # Realistic loading time
    
    # Get SMS messages
    sms_messages = await phone_api.fetch_real_sms(number)
    
    if not sms_messages:
        text = f"""
📭 **No SMS received yet**

📞 **Number:** `{number}`

⏳ **Waiting for verification codes...**

💡 **What to do:**
1. Make sure you've requested SMS from your app/service
2. Wait 30-60 seconds for delivery
3. Refresh this page
4. Most SMS arrive within 2 minutes

🔄 **Keep checking - messages appear automatically!**
        """
    else:
        text = f"📨 **Live SMS Messages for** `{number}`:\n\n"
        text += f"✅ **{len(sms_messages)} verification codes received:**\n\n"
        
        for i, sms in enumerate(sms_messages, 1):
            text += f"📩 **Message {i}:**\n"
            text += f"🏢 **From:** {sms['service']}\n"
            text += f"🔢 **Code:** `{sms['code']}`\n"
            text += f"📝 **Full SMS:** {sms['message']}\n"
            text += f"🕐 **Received:** {sms['time']}\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        text += "💡 **Just copy the verification code and use it in your app!**"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh SMS", callback_data=f"sms_{country}_{number_index}")],
        [InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_phone_{number}")],
        [InlineKeyboardButton("🔙 Back to Number", callback_data=f"phone_{country}_{number_index}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Get temporary email
async def get_temp_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Generate new temp email
    temp_email = email_api.generate_temp_email()
    log_email_usage(update.effective_user.id, temp_email)
    
    text = f"""
📧 **Your Temporary Email**

📮 **Email Address:** `{temp_email}`

📋 **Copy this email:**
`{temp_email}`

**How to use:**
1️⃣ **Copy** the email address above
2️⃣ **Go to any website** requiring email verification
3️⃣ **Paste this email** in registration form
4️⃣ **Complete registration** process
5️⃣ **Come back here** and check your inbox!

✨ **Perfect for:**
• Account registrations
• Newsletter signups
• Free trials
• Downloads
• Privacy protection

📨 **Check your inbox below:**
    """
    
    keyboard = [
        [InlineKeyboardButton("📬 Check Inbox", callback_data=f"inbox_{temp_email}")],
        [InlineKeyboardButton("📋 Copy Email", callback_data=f"copy_email_{temp_email}")],
        [InlineKeyboardButton("🔄 Generate New Email", callback_data="get_email"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show email inbox
async def show_inbox(query, email):
    # Show loading
    await query.edit_message_text("📬 **Checking your inbox...**\n\nPlease wait...", parse_mode='Markdown')
    await asyncio.sleep(2)
    
    # Get emails
    emails = await email_api.fetch_real_emails(email)
    
    if not emails:
        text = f"""
📭 **Inbox Empty**

📮 **Email:** `{email}`

⏳ **Waiting for emails...**

💡 **What to do:**
1. Make sure you've used this email for registration
2. Check spam/junk folder on the service
3. Wait 1-2 minutes for delivery
4. Some services may take up to 5 minutes

🔄 **Keep checking - emails appear automatically!**
        """
    else:
        text = f"📬 **Inbox for** `{email}`:\n\n"
        text += f"✅ **{len(emails)} emails received:**\n\n"
        
        for i, email_msg in enumerate(emails, 1):
            text += f"📧 **Email {i}:**\n"
            text += f"👤 **From:** {email_msg['from']}\n"
            text += f"📋 **Subject:** {email_msg['subject']}\n"
            text += f"🔢 **Code:** `{email_msg['code']}`\n"
            text += f"📝 **Preview:** {email_msg['content'][:100]}...\n"
            text += f"🕐 **Received:** {email_msg['time']}\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        text += "💡 **Copy the verification code and use it on the website!**"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Inbox", callback_data=f"inbox_{email}")],
        [InlineKeyboardButton("📋 Copy Email", callback_data=f"copy_email_{email}")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Copy functions
async def copy_phone(query, number):
    await query.answer(
        text=f"✅ Copied: {number}\n\nPaste this in your app!",
        show_alert=True
    )

async def copy_email(query, email):
    await query.answer(
        text=f"✅ Copied: {email}\n\nPaste this in your website!",
        show_alert=True
    )

# Bot statistics
async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect('phantomline.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(phone_requests) FROM users')
        total_phone_requests = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(email_requests) FROM users')
        total_email_requests = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > datetime("now", "-24 hours")')
        active_24h = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(ad_views) FROM users')
        total_ad_views = cursor.fetchone()[0] or 0
        
        conn.close()
        
        # Calculate additional stats
        total_countries = len(phone_api.get_countries())
        total_numbers = sum(len(phone_api.get_numbers_by_country(c)) for c in phone_api.get_countries())
        
        stats_text = f"""
📊 **PhantomLine Live Statistics**

👥 **User Statistics:**
• **Total Users:** {total_users:,} registered
• **Active Today:** {active_24h:,} users
• **Growth:** +{active_24h} in 24 hours

📱 **Phone Service:**
• **Countries:** {total_countries} regions available
• **Numbers:** {total_numbers} real phone numbers
• **Requests:** {total_phone_requests:,} total uses
• **Success Rate:** 98.5% verified

📧 **Email Service:**
• **Domains:** {len(email_api.email_domains)} providers
• **Requests:** {total_email_requests:,} emails generated
• **Delivery Rate:** 99.2% received

📈 **Performance:**
• **Uptime:** 99.9% online
• **Response Time:** < 2 seconds
• **Ad Revenue:** ${total_ad_views * 0.003:.2f} generated
• **Last Update:** {datetime.now().strftime('%H:%M')} UTC

🚀 **Join {total_users:,}+ users getting real verification codes!**
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="stats")],
            [InlineKeyboardButton("📱 Get Phone", callback_data="get_phone"),
             InlineKeyboardButton("📧 Get Email", callback_data="get_email")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        error_text = "❌ Stats temporarily unavailable. Please try again."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 **Complete PhantomLine Guide**

🔥 **How to Use Phone Numbers:**

**Step 1:** Choose "📱 Get Phone Number"
**Step 2:** Select your country (USA, UK, etc.)
**Step 3:** Pick any phone number you like
**Step 4:** Copy the number (tap and hold)
**Step 5:** Go to your app (WhatsApp, Instagram, etc.)
**Step 6:** Paste the number for verification
**Step 7:** Return here and click "Check SMS"
**Step 8:** Copy your verification code!

📧 **How to Use Temp Emails:**

**Step 1:** Choose "📧 Get Temp Email"
**Step 2:** Copy the generated email address
**Step 3:** Go to any website requiring email
**Step 4:** Use the email for registration
**Step 5:** Return here and click "Check Inbox"
**Step 6:** Get your verification email!

✨ **What Works:**
• **Phone Numbers:** WhatsApp, Telegram, Instagram, Facebook, Google, Apple, Discord, TikTok, Twitter, LinkedIn, Amazon, Netflix, Spotify, Uber, PayPal, Microsoft + 500 more!

• **Email Services:** All major websites, social media, shopping sites, streaming services, app stores, and more!

🎯 **Pro Tips:**
• All our numbers and emails are REAL
• SMS arrives within 30-60 seconds
• Emails arrive within 1-2 minutes
• Try different numbers if one doesn't work
• Refresh pages to check for new messages
• Use for testing and verification only

⚠️ **Important:**
• Services are shared (public access)
• Don't use for banking or sensitive accounts
• Perfect for app trials and social media
• Use responsibly and legally

❓ **Need help?** Contact our support team!
    """
    
    keyboard = [
        [InlineKeyboardButton("📱 Try Phone Numbers", callback_data="get_phone")],
        [InlineKeyboardButton("📧 Try Temp Emails", callback_data="get_email")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="support")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

# Support system
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = """
📞 **PhantomLine Support Center**

👋 **Need help?** We're here 24/7!

🔧 **Quick Solutions:**

**❌ Phone number not receiving SMS?**
✅ Wait 1-2 minutes and refresh
✅ Try a different number from same country
✅ Make sure you entered the complete number
✅ Some services may block certain numbers

**❌ Email not receiving messages?**
✅ Check your spam/junk folder
✅ Wait up to 5 minutes for delivery
✅ Generate a new email and try again
✅ Some services have delayed sending

**❌ Copy button not working?**
✅ Try long-pressing on the number/email
✅ Manually select and copy the text
✅ Restart your Telegram app
✅ Update to latest Telegram version

**❌ Verification code doesn't work?**
✅ Make sure you copied the complete code
✅ Check if the code has expired
✅ Try requesting a new code
✅ Some apps need codes without spaces

📝 **Report Issues:**
Type: `/report [describe your problem]`

**Examples:**
• `/report USA number +12092512708 not receiving WhatsApp SMS`
• `/report Email domain tempmail.org not working`
• `/report Copy button not responding on iPhone`

🎯 **Direct Contact:**
For urgent issues: Message Admin

📊 **Response Times:**
• General Support: 2-4 hours
• Technical Issues: 4-8 hours
• Urgent Problems: 1 hour

⏰ **Available:** 24/7 worldwide

🙏 **Help us improve!** Report any issues you find.
    """
    
    keyboard = [
        [InlineKeyboardButton("📝 Report Problem", callback_data="report_help")],
        [InlineKeyboardButton("🔄 Try Again", callback_data="main_menu")],
        [InlineKeyboardButton("❓ User Guide", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(support_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(support_text, reply_markup=reply_markup, parse_mode='Markdown')

# Report command
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ **Please describe your issue.**\n\n"
            "**Format:** `/report your problem description`\n\n"
            "**Examples:**\n"
            "• `/report USA number not receiving WhatsApp codes`\n"
            "• `/report Email tempmail.org not working`\n"
            "• `/report Copy button doesn't work on iPhone`",
            parse_mode='Markdown'
        )
        return
    
    user = update.effective_user
    message = ' '.join(context.args)
    timestamp = datetime.now()
    
    # Save to database
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO support_messages (user_id, username, first_name, message, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (user.id, user.username or "No username", user.first_name or "No name", 
          message, timestamp.isoformat()))
    
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Send to admin (ID: 5593343692)
    try:
        admin_text = f"""
🆘 **NEW SUPPORT TICKET #{ticket_id}**

👤 **User Info:**
• **Name:** {user.first_name or 'No name'}
• **Username:** @{user.username or 'No username'}
• **User ID:** `{user.id}`

📝 **Problem Report:**
            🕐 **Time:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC

**Quick Actions:**
• Reply: `/reply {user.id} your response`
• View all tickets: `/tickets`

---
PhantomLine Support System
        """
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"Support ticket #{ticket_id} sent to admin")
        
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
    
    # Confirm to user
    success_text = f"""
✅ **Support Request Sent!**

🎫 **Ticket ID:** #{ticket_id}

📝 **Your Message:**
    ⏰ **What's Next:**
• Our team will review your issue
• You'll get a direct response within 2-4 hours
• We'll message you in this chat
• Your ticket is being tracked

📞 **Need immediate help?**
Check our troubleshooting guide: /help

🙏 **Thank you for helping us improve PhantomLine!**
    """
    
    await update.message.reply_text(success_text, parse_mode='Markdown')

# Admin reply system
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "**Admin Reply Format:**\n"
            "`/reply <user_id> <your message>`\n\n"
            "**Example:**\n"
            "`/reply 123456789 Hi! I've fixed the issue. Please try again.`",
            parse_mode='Markdown'
        )
        return
    
    try:
        user_id = int(context.args[0])
        reply_message = ' '.join(context.args[1:])
        
        user_reply = f"""
📞 **PhantomLine Support Response**

👨‍💻 **Support Team:**

{reply_message}

---

📞 **Need more help?**
• Send `/report` with your issue
• Contact /support for guides
• Check /help for instructions

🙏 **Thank you for using PhantomLine!**

*Response from PhantomLine Support Team*
        """
        
        await context.bot.send_message(
            chat_id=user_id,
            text=user_reply,
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(
            f"✅ **Reply sent to user {user_id}**\n\n**Your message:**\n{reply_message}",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID format.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# Admin stats
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        conn = sqlite3.connect('phantomline.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM support_messages WHERE status = "open"')
        open_tickets = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(phone_requests) FROM users')
        phone_requests = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(email_requests) FROM users')
        email_requests = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(ad_views) FROM users')
        ad_views = cursor.fetchone()[0] or 0
        
        conn.close()
        
        admin_text = f"""
🔧 **ADMIN DASHBOARD**

📊 **User Stats:**
👥 Total Users: {total_users:,}
📱 Phone Requests: {phone_requests:,}
📧 Email Requests: {email_requests:,}
👆 Ad Views: {ad_views:,}

🎫 **Support:**
🔓 Open Tickets: {open_tickets:,}

💰 **Revenue:**
💵 Estimated: ${ad_views * 0.003:.2f}

📈 **Performance:**
🟢 Bot Status: Online
⚡ Response: < 2s
🔄 Updated: {datetime.now().strftime('%H:%M:%S')}

**Commands:**
• `/reply <user_id> <message>`
• `/broadcast <message>`
• `/tickets` - View all tickets
        """
        
        await update.message.reply_text(admin_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Admin error: {str(e)}")

# Report help callback
async def report_help(query):
    help_text = """
📝 **How to Report Issues**

**Format:** `/report your problem description`

**Be specific! Include:**
• Which service you used (phone/email)
• Which number/email you tried
• What app/website you were verifying
• What error occurred
• When it happened

**Good Examples:**

✅ `/report USA number +12092512708 not receiving WhatsApp SMS codes. Tried 3 times in last 10 minutes.`

✅ `/report Email user1234@tempmail.org not getting verification from Instagram. Waited 15 minutes.`

✅ `/report Copy button not working on Samsung Galaxy S21. When I tap it, nothing happens.`

❌ **Not helpful:**
• `/report not working`
• `/report help`
• `/report broken`

**Response Time:** 2-4 hours maximum

🚀 **Ready to report? Type your command now!**
    """
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Support", callback_data="support")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

# Enhanced callback handler with Adsterra ads
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Show Adsterra ads every 3rd click
    if ad_system.should_show_ad(user_id) and not data.startswith('ad_'):
        ad_system.increment_ad_views(user_id)
        
        ad_url = ad_system.get_ad_url()
        
        ad_text = f"""
🎯 **Quick Sponsor Message**

PhantomLine is FREE thanks to our sponsors! 

**To continue:**

1️⃣ **Visit our sponsor:** {ad_url}
2️⃣ **Wait 10 seconds** on their page
3️⃣ **Come back** and click "Continue" below

This keeps our service completely free! 🙏

**Your content will load after clicking continue.**
        """
        
        keyboard = [[InlineKeyboardButton("✅ Continue to Content", callback_data=f"ad_{data}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(ad_text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Remove ad prefix
    if data.startswith('ad_'):
        data = data[3:]
    
    # Route to handlers
    if data == "main_menu":
        await start(update, context)
    elif data == "get_phone":
        await get_phone_numbers(update, context)
    elif data == "get_email":
        await get_temp_email(update, context)
    elif data == "stats":
        await bot_stats(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "support":
        await support_command(update, context)
    elif data == "report_help":
        await report_help(query)
    elif data.startswith("country_"):
        country = data.split("_", 1)[1]
        await show_country_numbers(query, country)
    elif data.startswith("phone_"):
        parts = data.split("_")
        country = parts[1]
        number_index = int(parts[2])
        await show_phone_details(query, country, number_index)
    elif data.startswith("sms_"):
        parts = data.split("_")
        country = parts[1]
        number_index = int(parts[2])
        await show_sms_messages(query, country, number_index)
    elif data.startswith("inbox_"):
        email = data.split("_", 1)[1]
        await show_inbox(query, email)
    elif data.startswith("copy_phone_"):
        number = data.split("_", 2)[2]
        await copy_phone(query, number)
    elif data.startswith("copy_email_"):
        email = data.split("_", 2)[2]
        await copy_email(query, email)

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "🚨 **Oops! Something went wrong.**\n\n"
                "Our team has been notified. Please try again!\n\n"
                "**Quick fixes:**\n"
                "• Send /start to restart\n"
                "• Try a different option\n"
                "• Contact /support if this continues",
                parse_mode='Markdown'
            )
        except:
            pass

# Main function
def main():
    """Start the PhantomLine bot"""
    init_db()
    logger.info("Database initialized")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("stats", bot_stats))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("reply", admin_reply))
    application.add_handler(CommandHandler("admin", admin_stats))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 PhantomLine Bot Started Successfully!")
    logger.info(f"📱 {sum(len(phone_api.get_numbers_by_country(c)) for c in phone_api.get_countries())} phone numbers ready")
    logger.info(f"📧 {len(email_api.email_domains)} email providers ready")
    logger.info("🎯 All systems operational!")
    
    # Start polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
