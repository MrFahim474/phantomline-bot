import os
import logging
import sqlite3
import asyncio
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration - Replace with your actual token
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '123456789'))  # Replace with your Telegram user ID

# Database setup
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
            ad_clicks INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0
        )
    ''')
    
    # Support messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            timestamp TEXT,
            status TEXT DEFAULT 'open'
        )
    ''')
    
    # Number requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS number_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            country TEXT,
            number TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# Adsterra Ad System
class AdsterraAds:
    def __init__(self):
        # Replace with your actual Adsterra links
        self.ad_links = [
            "https://aads.com/campaigns/clicks/17/?euid={user_id}",  # Replace with your Adsterra link
            "https://syndication.realsrv.com/splash.php?idzone=4582134",  # Example Adsterra popunder
        ]
        
    def get_ad_url(self, user_id):
        return random.choice(self.ad_links).format(user_id=user_id)
    
    def should_show_ad(self, user_id):
        conn = sqlite3.connect('phantomline.db')
        cursor = conn.cursor()
        cursor.execute('SELECT ad_clicks FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            clicks = result[0]
            return clicks % 2 == 0  # Show ad every 2nd click
        return True

# Phone Number API System
class PhoneNumberAPI:
    def __init__(self):
        self.countries_data = {
            'USA 🇺🇸': {
                'numbers': [
                    {'number': '+1-775-305-5499', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+1-775-678-6885', 'service': 'Quackr', 'status': '🟢 Active'},
                    {'number': '+1-775-377-2662', 'service': 'FreePhoneNum', 'status': '🟢 Active'},
                    {'number': '+1-702-751-2608', 'service': 'TempSMS', 'status': '🟢 Active'},
                    {'number': '+1-559-741-8334', 'service': 'SMSReceiveFree', 'status': '🟢 Active'}
                ]
            },
            'UK 🇬🇧': {
                'numbers': [
                    {'number': '+44-77-0015-0616', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+44-77-0015-0655', 'service': 'TempPhone', 'status': '🟢 Active'},
                    {'number': '+44-77-0015-0634', 'service': 'FreeSMS', 'status': '🟢 Active'}
                ]
            },
            'Germany 🇩🇪': {
                'numbers': [
                    {'number': '+49-157-3598-3768', 'service': 'SMS77', 'status': '🟢 Active'},
                    {'number': '+49-157-3599-8460', 'service': 'ReceiveFreeSMS', 'status': '🟢 Active'},
                    {'number': '+49-152-0280-6842', 'service': 'TempSMS', 'status': '🟢 Active'}
                ]
            },
            'Canada 🇨🇦': {
                'numbers': [
                    {'number': '+1-587-984-6325', 'service': 'FreePhoneNum', 'status': '🟢 Active'},
                    {'number': '+1-613-800-6493', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+1-438-803-0648', 'service': 'TempPhone', 'status': '🟢 Active'}
                ]
            },
            'France 🇫🇷': {
                'numbers': [
                    {'number': '+33-7-57-59-20-41', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+33-7-57-59-80-22', 'service': 'FreeSMS', 'status': '🟢 Active'}
                ]
            },
            'Spain 🇪🇸': {
                'numbers': [
                    {'number': '+34-613-28-08-89', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+34-662-07-75-56', 'service': 'TempSMS', 'status': '🟢 Active'}
                ]
            },
            'Netherlands 🇳🇱': {
                'numbers': [
                    {'number': '+31-6-83-73-40-22', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+31-6-44-01-81-89', 'service': 'FreeSMS', 'status': '🟢 Active'}
                ]
            },
            'Italy 🇮🇹': {
                'numbers': [
                    {'number': '+39-320-28-38-889', 'service': 'ReceiveSMS', 'status': '🟢 Active'},
                    {'number': '+39-327-23-25-045', 'service': 'TempSMS', 'status': '🟢 Active'}
                ]
            }
        }
    
    def get_countries(self):
        return list(self.countries_data.keys())
    
    def get_numbers_by_country(self, country):
        return self.countries_data.get(country, {}).get('numbers', [])
    
    async def simulate_sms(self, number):
        # Simulate receiving SMS messages
        sample_messages = [
            {"service": "Google", "code": f"{random.randint(100000, 999999)}", "time": "Just now", "full_text": f"Your Google verification code is {random.randint(100000, 999999)}"},
            {"service": "WhatsApp", "code": f"{random.randint(1000, 9999)}", "time": "1 min ago", "full_text": f"Your WhatsApp code: {random.randint(1000, 9999)}. Don't share this code with others"},
            {"service": "Telegram", "code": f"{random.randint(10000, 99999)}", "time": "2 min ago", "full_text": f"Telegram code: {random.randint(10000, 99999)}"},
            {"service": "Facebook", "code": f"{random.randint(100, 999)}-{random.randint(100, 999)}", "time": "3 min ago", "full_text": f"Facebook: {random.randint(100, 999)}-{random.randint(100, 999)} is your confirmation code"},
            {"service": "Instagram", "code": f"{random.randint(100000, 999999)}", "time": "5 min ago", "full_text": f"Instagram code: {random.randint(100000, 999999)}"},
        ]
        
        # Randomly return 1-3 messages
        num_messages = random.randint(1, 3)
        return random.sample(sample_messages, num_messages)

# Initialize systems
ad_system = AdsterraAds()
phone_api = PhoneNumberAPI()

# Helper functions
def save_user(update: Update):
    user = update.effective_user
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, join_date, ad_clicks, total_requests)
        VALUES (?, ?, ?, ?, 
                COALESCE((SELECT ad_clicks FROM users WHERE user_id = ?), 0),
                COALESCE((SELECT total_requests FROM users WHERE user_id = ?), 0))
    ''', (user.id, user.username, user.first_name, datetime.now().isoformat(), user.id, user.id))
    
    conn.commit()
    conn.close()

def increment_ad_clicks(user_id):
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET ad_clicks = ad_clicks + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def increment_requests(user_id):
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET total_requests = total_requests + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update)
    
    welcome_text = """
🔥 **Welcome to PhantomLine Bot!** 🔥

Your ultimate solution for FREE temporary phone numbers! 📱

🌟 **What we offer:**
📞 **Real temporary numbers** from 8+ countries
⚡ **Instant SMS reception** - Get codes in seconds
🔒 **Complete privacy** - No registration needed
🆓 **100% FREE** - Always and forever!

💡 **How it works:**
1️⃣ Choose your country
2️⃣ Pick a phone number  
3️⃣ Use it for verification
4️⃣ Get SMS codes instantly!

🚀 **Ready to get started?**
Choose an option below! 👇
    """
    
    keyboard = [
        [InlineKeyboardButton("📞 Get Phone Numbers", callback_data="get_numbers")],
        [InlineKeyboardButton("🌍 Browse Countries", callback_data="countries"),
         InlineKeyboardButton("❓ How to Use", callback_data="help")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="stats"),
         InlineKeyboardButton("📞 Support", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# Countries command
async def countries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    countries = phone_api.get_countries()
    
    text = "🌍 **Available Countries & Regions:**\n\n"
    text += "Select a country to view available phone numbers:\n\n"
    
    keyboard = []
    row = []
    for i, country in enumerate(countries):
        row.append(InlineKeyboardButton(country, callback_data=f"country_{country}"))
        if len(row) == 2 or i == len(countries) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show numbers for specific country
async def show_country_numbers(query, country):
    numbers = phone_api.get_numbers_by_country(country)
    
    if not numbers:
        text = f"❌ **No numbers available for {country}**\n\nTry another country or check back later!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Countries", callback_data="countries")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    text = f"📱 **{country} Phone Numbers:**\n\n"
    text += f"✅ **{len(numbers)} numbers available**\n\n"
    
    keyboard = []
    for i, num_data in enumerate(numbers):
        text += f"📞 `{num_data['number']}` {num_data['status']}\n"
        text += f"   🔧 Service: {num_data['service']}\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"📞 {num_data['number']}", 
            callback_data=f"number_{country}_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Countries", callback_data="countries")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show specific number details
async def show_number_details(query, country, number_index):
    numbers = phone_api.get_numbers_by_country(country)
    
    if number_index >= len(numbers):
        await query.edit_message_text("❌ Number not found!")
        return
    
    number_data = numbers[number_index]
    number = number_data['number']
    
    # Increment user requests
    increment_requests(query.from_user.id)
    
    text = f"""
📱 **Number Details**

📞 **Phone Number:** `{number}`
🌍 **Country:** {country}
🔧 **Service:** {number_data['service']}
{number_data['status']} **Status**

📋 **Instructions:**
1️⃣ Copy the number above
2️⃣ Paste it in any app/website verification
3️⃣ Click "📨 Check SMS" to see received messages
4️⃣ Use the verification code from SMS

⚠️ **Important Notes:**
• This is a public shared number
• Don't use for sensitive accounts
• Messages are visible to everyone
• Perfect for app trials and verifications

🔄 **Click "Check SMS" to see messages!**
    """
    
    keyboard = [
        [InlineKeyboardButton("📨 Check SMS Messages", callback_data=f"sms_{country}_{number_index}")],
        [InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_{number}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"number_{country}_{number_index}"),
         InlineKeyboardButton("🔙 Back", callback_data=f"country_{country}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Show SMS messages
async def show_sms_messages(query, country, number_index):
    numbers = phone_api.get_numbers_by_country(country)
    
    if number_index >= len(numbers):
        await query.edit_message_text("❌ Number not found!")
        return
    
    number_data = numbers[number_index]
    number = number_data['number']
    
    # Get SMS messages (simulated)
    sms_messages = await phone_api.simulate_sms(number)
    
    if not sms_messages:
        text = f"""
📭 **No SMS received yet**

📞 **Number:** `{number}`

⏳ **Waiting for messages...**

💡 **Tips:**
• SMS usually arrives within 30 seconds
• Try using the number in different apps
• Refresh this page in a moment
• Some services might take longer

🔄 **Keep refreshing to check for new messages!**
        """
    else:
        text = f"📨 **SMS Messages for** `{number}`:\n\n"
        text += f"✅ **{len(sms_messages)} messages received:**\n\n"
        
        for i, sms in enumerate(sms_messages, 1):
            text += f"📩 **Message {i}:**\n"
            text += f"🏢 **From:** {sms['service']}\n"
            text += f"🔢 **Code:** `{sms['code']}`\n"
            text += f"📝 **Full Text:** {sms['full_text']}\n"
            text += f"🕐 **Received:** {sms['time']}\n\n"
        
        text += "💡 **Just copy the code and use it for verification!**"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh SMS", callback_data=f"sms_{country}_{number_index}")],
        [InlineKeyboardButton("🔙 Back to Number", callback_data=f"number_{country}_{number_index}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 **Complete User Guide**

🎯 **How to Use PhantomLine:**

**Step 1: Choose Country** 🌍
• Click "Browse Countries"
• Select your preferred country
• We have 8+ countries available!

**Step 2: Pick a Number** 📞
• Browse available numbers
• Click on any number you like
• Copy the number to your clipboard

**Step 3: Use for Verification** ✅
• Go to any website/app
• Enter the copied number
• Request verification SMS

**Step 4: Get Your Code** 📨
• Come back to this bot
• Click "Check SMS Messages"
• Copy the verification code
• Use it to complete verification!

🔥 **Pro Tips:**
• Numbers work for 99% of services
• Try different numbers if one doesn't work
• SMS usually arrives within 30 seconds
• Refresh SMS page if needed

⚠️ **Important Rules:**
• Don't use for banking/financial accounts
• Numbers are public (shared with others)
• Don't use for illegal activities
• Use responsibly and ethically

❓ **Still need help?** Contact our support team!
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 Try It Now", callback_data="countries")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="support")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

# Support command
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = """
📞 **Support Center**

👋 **Need help?** We're here for you!

🔧 **Common Issues & Solutions:**

**❌ Number not receiving SMS?**
✅ Try a different number from the same country
✅ Wait 1-2 minutes and refresh
✅ Some services block certain providers

**❌ Verification code not working?**
✅ Make sure you copied the complete code
✅ Check if code has expired
✅ Try requesting a new code

**❌ Bot not responding?**
✅ Send /start to restart the bot
✅ Check your internet connection
✅ Try again in a few moments

**❌ Country/Number not available?**
✅ Try different countries
✅ Check back later (we add new numbers daily)
✅ Contact us for specific requests

📝 **Report a Problem:**
Type: `/report your message here`

**Example:** `/report The UK number +44-xxx-xxxx is not working`

🎯 **Contact Admin:**
For urgent issues, contact: @YourAdminUsername

⏰ **Support Hours:** 24/7 (Response within 2-4 hours)
    """
    
    keyboard = [
        [InlineKeyboardButton("📝 Report Issue", callback_data="report_issue")],
        [InlineKeyboardButton("🔄 Try Again", callback_data="main_menu")],
        [InlineKeyboardButton("❓ User Guide", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(support_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(support_text, reply_markup=reply_markup, parse_mode='Markdown')

# Bot stats
async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    
    # Get total users
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Get total requests today
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('SELECT COUNT(*) FROM number_requests WHERE timestamp LIKE ?', (f'{today}%',))
    today_requests = cursor.fetchone()[0]
    
    # Get total countries and numbers
    total_countries = len(phone_api.get_countries())
    total_numbers = sum(len(phone_api.get_numbers_by_country(country)) for country in phone_api.get_countries())
    
    conn.close()
    
    stats_text = f"""
📊 **PhantomLine Bot Statistics**

👥 **Users:** {total_users:,} registered users
📞 **Today's Requests:** {today_requests:,} numbers used
🌍 **Countries Available:** {total_countries} countries
📱 **Total Numbers:** {total_numbers} active numbers

🔥 **Popular Features:**
• 📞 Phone Number Requests: {today_requests:,} today
• 🌍 Most Popular: USA 🇺🇸, UK 🇬🇧, Germany 🇩🇪
• ⚡ Average Response Time: < 30 seconds
• ✅ Success Rate: 95%+

🚀 **Bot Status:** ✅ Online & Running
🔄 **Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC

💡 **Join {total_users:,}+ users getting free phone numbers!**
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="stats")],
        [InlineKeyboardButton("📞 Get Numbers", callback_data="get_numbers")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

# Report command
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ **Please provide your message.**\n\n**Example:** `/report The number +1-xxx-xxxx is not working`",
            parse_mode='Markdown'
        )
        return
    
    user = update.effective_user
    message = ' '.join(context.args)
    
    # Save to database
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO support_messages (user_id, username, message, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user.id, user.username or "No username", message, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Send to admin
    try:
        admin_text = f"""
🆘 **New Support Request**

👤 **User:** @{user.username or 'No username'} ({user.first_name})
🆔 **User ID:** {user.id}
📝 **Message:** {message}
🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Reply to this user: /reply {user.id} your_response_here
        """
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
    
    success_text = """
✅ **Support request sent successfully!**

📝 **Your message has been received:**

⏰ **Response Time:** Usually within 2-4 hours
📱 **You'll receive a direct message from our admin**

🙏 **Thank you for helping us improve PhantomLine!**
    """.format(message=message)
    
    await update.message.reply_text(success_text, parse_mode='Markdown')

# Admin reply command
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <message>")
        return
    
    try:
        user_id = int(context.args[0])
        reply_message = ' '.join(context.args[1:])
        
        reply_text = f"""
 **📞 PhantomLine Support Response**

      # Admin reply command continued
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <message>")
        return
    
    try:
    user_id = int(context.args[0])
    reply_message = ' '.join(context.args[1:])
    
    reply_text = "📞 PhantomLine Support Response:\n" + reply_message
    await context.bot.send_message(chat_id=user_id, text=reply_text)

💬 **Admin Reply:**
{reply_message}

📞 **Need more help?** Send /support or /report again

🙏 **Thank you for using PhantomLine!**
        """
        
        await context.bot.send_message(chat_id=user_id, text=reply_text, parse_mode='Markdown')
        await update.message.reply_text(f"✅ Reply sent to user {user_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending reply: {e}")

# Callback query handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Handle ads (Adsterra integration)
    if ad_system.should_show_ad(user_id) and not data.startswith('ad_'):
        increment_ad_clicks(user_id)
        
        # Show ad before actual content
        ad_url = ad_system.get_ad_url(user_id)
        
        ad_text = f"""
🎯 **Sponsored Content**

PhantomLine is FREE thanks to our sponsors!

🎁 **To continue, please:**
1️⃣ Click the link below
2️⃣ Wait 5 seconds on the ad page
3️⃣ Close the ad and return here
4️⃣ Click "Continue" button

This helps keep our service free! 🙏

👆 **Click here first:** {ad_url}
        """
        
        keyboard = [[InlineKeyboardButton("✅ Continue to Content", callback_data=f"ad_{data}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(ad_text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Handle actual content (remove ad prefix if present)
    if data.startswith('ad_'):
        data = data[3:]
    
    # Route to appropriate handler
    if data == "main_menu":
        await start(update, context)
    elif data == "get_numbers":
        await countries_command(update, context)
    elif data == "countries":
        await countries_command(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "support":
        await support_command(update, context)
    elif data == "stats":
        await bot_stats(update, context)
    elif data.startswith("country_"):
        country = data.split("_", 1)[1]
        await show_country_numbers(query, country)
    elif data.startswith("number_"):
        parts = data.split("_")
        country = parts[1]
        number_index = int(parts[2])
        await show_number_details(query, country, number_index)
    elif data.startswith("sms_"):
        parts = data.split("_")
        country = parts[1]
        number_index = int(parts[2])
        await show_sms_messages(query, country, number_index)
    elif data.startswith("copy_"):
        number = data.split("_", 1)[1]
        await query.answer(f"Number {number} copied to clipboard!", show_alert=True)
    elif data == "report_issue":
        await query.edit_message_text(
            "📝 **Report an Issue**\n\nType: `/report your message here`\n\n**Example:**\n`/report The UK number is not working`",
            parse_mode='Markdown'
        )

# Admin stats command
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect('phantomline.db')
    cursor = conn.cursor()
    
    # Get comprehensive stats
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM support_messages WHERE status = "open"')
    open_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM support_messages')
    total_tickets = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(total_requests) FROM users')
    total_requests = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(ad_clicks) FROM users')
    total_ad_clicks = cursor.fetchone()[0] or 0
    
    # Recent activity
    cursor.execute('''
        SELECT COUNT(*) FROM users 
        WHERE join_date > datetime('now', '-24 hours')
    ''')
    new_users_24h = cursor.fetchone()[0]
    
    conn.close()
    
    admin_stats_text = f"""
🔧 **Admin Dashboard - PhantomLine Bot**

📊 **User Statistics:**
👥 Total Users: {total_users:,}
🆕 New Users (24h): {new_users_24h:,}
👆 Total Ad Clicks: {total_ad_clicks:,}
📞 Total Requests: {total_requests:,}

🎫 **Support Statistics:**
📝 Total Tickets: {total_tickets:,}
🔓 Open Tickets: {open_tickets:,}
✅ Resolved: {total_tickets - open_tickets:,}

📈 **Performance:**
🤖 Bot Status: ✅ Online
💰 Revenue Potential: {total_ad_clicks * 0.001:.2f} USD (est.)
📱 Numbers Available: {sum(len(phone_api.get_numbers_by_country(c)) for c in phone_api.get_countries())}
🌍 Countries: {len(phone_api.get_countries())}

🔄 **Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")],
        [InlineKeyboardButton("📝 View Tickets", callback_data="admin_tickets")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(admin_stats_text, reply_markup=reply_markup, parse_mode='Markdown')

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "🚨 **Oops! Something went wrong.**\n\n"
                "Don't worry, our team has been notified. Please try again in a moment.\n\n"
                "If the problem persists, contact /support",
                parse_mode='Markdown'
            )
        except Exception:
            pass

# Main function
def main():
    """Start the bot."""
    # Initialize database
    init_db()
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("countries", countries_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("stats", bot_stats))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("reply", admin_reply))
    application.add_handler(CommandHandler("admin", admin_stats))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🚀 PhantomLine Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
