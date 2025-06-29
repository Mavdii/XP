#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Telegram Bot with XP System, Coins, Shop, and Professional Features
Compatible with Vercel deployment
"""

import os
import asyncio
import logging
import json
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Response

app = FastAPI()

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# Supabase imports
from supabase import create_client, Client

# Configuration
class Config:
    # Telegram Bot Configuration
    API_ID = "YOUR_API_ID"  # Replace with your API ID
    API_HASH = "YOUR_API_HASH"  # Replace with your API Hash
    BOT_TOKEN = "YOUR_BOT_TOKEN"  # Replace with your Bot Token
    
    # Supabase Configuration
    SUPABASE_URL = "YOUR_SUPABASE_URL"  # Replace with your Supabase URL
    SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"  # Replace with your Supabase Anon Key
    
    # XP and Coin System
    XP_PER_MESSAGE = 5
    COINS_PER_MESSAGE = 2
    DAILY_REWARD_COINS = 100
    DAILY_REWARD_XP = 50
    
    # Level System
    BASE_XP = 100
    XP_MULTIPLIER = 1.5
    
    # Rank Prices (in coins)
    RANK_PRICES = {
        "VIP": 5000,
        "Premium": 15000,
        "Admin": 50000
    }
    
    # Shop Items
    SHOP_ITEMS = {
        "🎯 Double XP (1 hour)": {"price": 500, "type": "boost", "duration": 3600},
        "💰 Coin Multiplier (1 hour)": {"price": 750, "type": "boost", "duration": 3600},
        "🌟 Custom Title": {"price": 2000, "type": "cosmetic"},
        "🎨 Profile Theme": {"price": 1500, "type": "cosmetic"},
        "🏆 Achievement Badge": {"price": 3000, "type": "cosmetic"}
    }

# Initialize Supabase client
supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Utility Functions
def format_number(num: int) -> str:
    """Format large numbers with K, M, B suffixes"""
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)

def get_rank_emoji(rank: str) -> str:
    """Get emoji for user rank"""
    rank_emojis = {
        "Newbie": "🌱",
        "Member": "👤",
        "VIP": "⭐",
        "Premium": "💎",
        "Admin": "👑",
        "Owner": "🔥"
    }
    return rank_emojis.get(rank, "👤")

def get_level_emoji(level: int) -> str:
    """Get emoji based on user level"""
    if level >= 100:
        return "🏆"
    elif level >= 50:
        return "💎"
    elif level >= 25:
        return "⭐"
    elif level >= 10:
        return "🌟"
    else:
        return "🌱"

def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Create a visual progress bar"""
    if total == 0:
        return "▱" * length
    
    filled = int((current / total) * length)
    return "▰" * filled + "▱" * (length - filled)

def time_until_next_day() -> str:
    """Calculate time until next day for daily reward"""
    now = datetime.now()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    diff = tomorrow - now
    
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    return f"{hours}h {minutes}m"

# Database Functions
async def get_or_create_user(user_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
    """Get user from database or create if doesn't exist"""
    try:
        # Try to get existing user
        result = supabase.table('users').select('*').eq('user_id', user_id).execute()
        
        if result.data:
            return result.data[0]
        
        # Create new user
        new_user = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'xp': 0,
            'level': 1,
            'coins': 100,  # Starting coins
            'rank': 'Newbie',
            'last_daily': None,
            'daily_streak': 0,
            'total_messages': 0,
            'join_date': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat()
        }
        
        result = supabase.table('users').insert(new_user).execute()
        return result.data[0]
        
    except Exception as e:
        logger.error(f"Database error in get_or_or_create_user: {e}")
        return None

async def update_user_xp(user_id: int, xp_gain: int, coins_gain: int) -> bool:
    """Update user XP and coins"""
    try:
        # Get current user data
        user = await get_or_create_user(user_id)
        if not user:
            return False
        
        new_xp = user['xp'] + xp_gain
        new_coins = user['coins'] + coins_gain
        new_level = calculate_level(new_xp)
        
        # Update user
        supabase.table('users').update({
            'xp': new_xp,
            'level': new_level,
            'coins': new_coins,
            'total_messages': user['total_messages'] + 1,
            'last_active': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        # Check for level up
        if new_level > user['level']:
            await log_level_up(user_id, user['level'], new_level)
            return True  # Level up occurred
        
        return False  # No level up
        
    except Exception as e:
        logger.error(f"Database error in update_user_xp: {e}")
        return False

def calculate_level(xp: int) -> int:
    """Calculate level based on XP"""
    level = 1
    required_xp = Config.BASE_XP
    
    while xp >= required_xp:
        xp -= required_xp
        level += 1
        required_xp = int(required_xp * Config.XP_MULTIPLIER)
    
    return level

def calculate_xp_for_level(level: int) -> int:
    """Calculate total XP required for a specific level"""
    total_xp = 0
    required_xp = Config.BASE_XP
    
    for i in range(1, level):
        total_xp += required_xp
        required_xp = int(required_xp * Config.XP_MULTIPLIER)
    
    return total_xp

async def log_transaction(user_id: int, transaction_type: str, amount: int, description: str):
    """Log user transactions"""
    try:
        supabase.table('transactions').insert({
            'user_id': user_id,
            'type': transaction_type,
            'amount': amount,
            'description': description,
            'timestamp': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error logging transaction: {e}")

async def log_level_up(user_id: int, old_level: int, new_level: int):
    """Log level up event"""
    try:
        supabase.table('level_ups').insert({
            'user_id': user_id,
            'old_level': old_level,
            'new_level': new_level,
            'timestamp': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error logging level up: {e}")

async def check_daily_reward(user_id: int) -> Dict[str, Any]:
    """Check if user can claim daily reward"""
    try:
        user = await get_or_create_user(user.id)
        if not user:
            return {"can_claim": False, "reason": "User not found"}
        
        last_daily = user.get('last_daily')
        if not last_daily:
            return {"can_claim": True, "streak": 0}
        
        last_daily_date = datetime.fromisoformat(last_daily).date()
        today = datetime.now().date()
        
        if last_daily_date == today:
            return {
                "can_claim": False, 
                "reason": "Already claimed today",
                "time_left": time_until_next_day()
            }
        
        # Check streak
        yesterday = today - timedelta(days=1)
        streak = user.get('daily_streak', 0)
        
        if last_daily_date == yesterday:
            streak += 1
        else:
            streak = 1
        
        return {"can_claim": True, "streak": streak}
        
    except Exception as e:
        logger.error(f"Error checking daily reward: {e}")
        return {"can_claim": False, "reason": "Database error"}

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Create or get user
    user_data = await get_or_create_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
🎉 **مرحباً {user.first_name}!** 🎉

🤖 **أهلاً بك في البوت المتقدم!**

✨ **الميزات المتاحة:**
🏆 نظام XP والمستويات
💰 نظام العملات والمكافآت
🛒 متجر الترقيات والعناصر
🎯 مهام وإنجازات يومية
⭐ رتب VIP و Premium
📊 إحصائيات مفصلة
🎮 ألعاب مصغرة

💡 **ابدأ بكتابة الرسائل لكسب XP والعملات!**

📋 استخدم /help لرؤية جميع الأوامر
👤 استخدم /me لرؤية ملفك الشخصي
🎁 استخدم /daily للمكافأة اليومية
"""
    
    keyboard = [
        [InlineKeyboardButton("📊 ملفي الشخصي", callback_data="profile")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop"), 
         InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")],
        [InlineKeyboardButton("📋 المساعدة", callback_data="help"),
         InlineKeyboardButton("📈 الإحصائيات", callback_data="stats")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = f"""
📋 **قائمة الأوامر المتاحة:**

🔹 **الأوامر الأساسية:**
/start - بدء البوت والترحيب
/help - عرض هذه القائمة
/me - عرض الملف الشخصي
/daily - المكافأة اليومية
/shop - متجر الترقيات

🔹 **أوامر المعلومات:**
/stats - إحصائياتك المفصلة
/leaderboard - قائمة المتصدرين
/rank - معلومات الرتب

🔹 **أوامر الألعاب:**
/game - الألعاب المصغرة
/dice - لعبة النرد
/coin - قذف العملة

🔹 **أوامر VIP/Premium:**
/upgrade - ترقية الرتبة
/transfer - تحويل العملات
/custom - تخصيص الملف الشخصي

💡 **نصائح:**
• اكتب رسائل في المجموعات لكسب XP والعملات
• احصل على المكافأة اليومية كل 24 ساعة
• اشتر الترقيات من المتجر لزيادة الأرباح
• ارتق إلى VIP أو Premium للميزات الإضافية
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /me command - show user profile"""
    user = update.effective_user
    user_data = await get_or_create_user(user.id, user.username, user.first_name)
    
    if not user_data:
        await update.message.reply_text("❌ حدث خطأ في جلب بياناتك!")
        return
    
    # Calculate XP for next level
    current_level = user_data['level']
    current_xp = user_data['xp']
    xp_for_current_level = calculate_xp_for_level(current_level)
    xp_for_next_level = calculate_xp_for_level(current_level + 1)
    xp_needed = xp_for_next_level - current_xp
    xp_progress = current_xp - xp_for_current_level
    xp_required_for_level = xp_for_next_level - xp_for_current_level
    
    # Create progress bar
    progress = create_progress_bar(xp_progress, xp_required_for_level, 15)
    
    # Format join date
    join_date = datetime.fromisoformat(user_data['join_date']).strftime("%Y-%m-%d")
    
    profile_text = f"""
👤 **الملف الشخصي**

🏷️ **الاسم:** {user_data['first_name']}
🆔 **المعرف:** @{user_data.get('username', 'غير محدد')}

{get_level_emoji(current_level)} **المستوى:** {current_level}
{get_rank_emoji(user_data['rank'])} **الرتبة:** {user_data['rank']}

⚡ **XP:** {format_number(current_xp)}
📊 **التقدم:** {progress} ({xp_progress}/{xp_required_for_level})
🎯 **XP للمستوى التالي:** {format_number(xp_needed)}

💰 **العملات:** {format_number(user_data['coins'])}
💬 **إجمالي الرسائل:** {format_number(user_data['total_messages'])}
🔥 **سلسلة المكافآت:** {user_data.get('daily_streak', 0)} يوم

📅 **تاريخ الانضمام:** {join_date}
"""
    
    keyboard = [
        [InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="detailed_stats")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="shop"),
         InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily")],
        [InlineKeyboardButton("⬆️ ترقية الرتبة", callback_data="upgrade_rank")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        profile_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily command - daily reward"""
    user = update.effective_user
    
    # Check if user can claim daily reward
    daily_check = await check_daily_reward(user.id)
    
    if not daily_check["can_claim"]:
        if "time_left" in daily_check:
            await update.message.reply_text(
                f"⏰ **لقد حصلت على المكافأة اليومية بالفعل!**\n\n"
                f"🕐 الوقت المتبقي: {daily_check['time_left']}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **خطأ:** {daily_check['reason']}",
                parse_mode='Markdown'
            )
        return
    
    # Calculate reward based on streak
    streak = daily_check["streak"]
    base_coins = Config.DAILY_REWARD_COINS
    base_xp = Config.DAILY_REWARD_XP
    
    # Bonus for streak
    streak_bonus = min(streak * 10, 200)  # Max 200% bonus
    total_coins = base_coins + (base_coins * streak_bonus // 100)
    total_xp = base_xp + (base_xp * streak_bonus // 100)
    
    # Update user
    try:
        user_data = await get_or_create_user(user.id)
        new_coins = user_data['coins'] + total_coins
        new_xp = user_data['xp'] + total_xp
        new_level = calculate_level(new_xp)
        
        supabase.table('users').update({
            'coins': new_coins,
            'xp': new_xp,
            'level': new_level,
            'last_daily': datetime.now().isoformat(),
            'daily_streak': streak
        }).eq('user_id', user.id).execute()
        
        # Log transaction
        await log_transaction(user.id, "daily_reward", total_coins, f"Daily reward (streak: {streak})")
        
        reward_text = f"""
🎁 **مكافأة يومية!**

💰 **العملات:** +{format_number(total_coins)}
⚡ **XP:** +{format_number(total_xp)}
🔥 **السلسلة:** {streak} يوم

{f"🎉 **مكافأة السلسلة:** +{streak_bonus}%" if streak_bonus > 0 else ""}

💡 **عد غداً للحصول على مكافأة أكبر!**
"""
        
        # Check for level up
        if new_level > user_data['level']:
            reward_text += f"\n🎊 **تهانينا! وصلت للمستوى {new_level}!**"
        
        keyboard = [
            [InlineKeyboardButton("📊 ملفي الشخصي", callback_data="profile")],
            [InlineKeyboardButton("🛒 المتجر", callback_data="shop")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            reward_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in daily command: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء منح المكافأة!")

async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /shop command"""
    user = update.effective_user
    user_data = await get_or_create_user(user.id)
    
    if not user_data:
        await update.message.reply_text("❌ حدث خطأ في جلب بياناتك!")
        return
    
    shop_text = f"""
🛒 **متجر الترقيات**

💰 **رصيدك:** {format_number(user_data['coins'])} عملة

🛍️ **العناصر المتاحة:**

"""
    
    keyboard = []
    
    for item_name, item_data in Config.SHOP_ITEMS.items():
        price = item_data["price"]
        can_afford = user_data['coins'] >= price
        status = "✅" if can_afford else "❌"
        
        shop_text += f"{status} **{item_name}**\n💰 السعر: {format_number(price)} عملة\n\n"
        
        if can_afford:
            callback_data = f"buy_{list(Config.SHOP_ITEMS.keys()).index(item_name)}"
            keyboard.append([InlineKeyboardButton(f"شراء {item_name}", callback_data=callback_data)])
    
    # Add rank upgrades
    shop_text += "⭐ **ترقيات الرتب:**\n\n"
    
    for rank, price in Config.RANK_PRICES.items():
        if user_data['rank'] != rank:
            can_afford = user_data['coins'] >= price
            status = "✅" if can_afford else "❌"
            
            shop_text += f"{status} **{get_rank_emoji(rank)} {rank}**\n💰 السعر: {format_number(price)} عملة\n\n"
            
            if can_afford:
                callback_data = f"upgrade_{rank.lower()}"
                keyboard.append([InlineKeyboardButton(f"ترقية إلى {rank}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        shop_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Message Handler for XP and Coins
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages to award XP and coins"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Only process group messages
    if chat.type not in ['group', 'supergroup']:
        return
    
    # Ignore bot messages
    if user.is_bot:
        return
    
    # Award XP and coins
    level_up = await update_user_xp(user.id, Config.XP_PER_MESSAGE, Config.COINS_PER_MESSAGE)
    
    # Notify on level up
    if level_up:
        user_data = await get_or_create_user(user.id)
        if user_data:
            level_up_text = f"""
🎊 **تهانينا {user.first_name}!**

{get_level_emoji(user_data['level'])} **وصلت للمستوى {user_data['level']}!**
⚡ **XP الحالي:** {format_number(user_data['xp'])}
💰 **العملات:** {format_number(user_data['coins'])}

🎁 **مكافأة المستوى:** +50 عملة
"""
            
            # Give level up bonus
            supabase.table('users').update({
                'coins': user_data['coins'] + 50
            }).eq('user_id', user.id).execute()
            
            await update.message.reply_text(
                level_up_text,
                parse_mode='Markdown'
            )

# Callback Query Handler
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "start":
        await start_command(update, context)
    elif data == "profile":
        await profile_command(update, context)
    elif data == "shop":
        await shop_command(update, context)
    elif data == "daily":
        await daily_command(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data.startswith("buy_"):
        await handle_shop_purchase(update, context, data)
    elif data.startswith("upgrade_"):
        await handle_rank_upgrade(update, context, data)
    else:
        await query.edit_message_text("❌ خيار غير صحيح!")

async def handle_shop_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Handle shop item purchases"""
    query = update.callback_query
    user = query.from_user
    
    try:
        item_index = int(callback_data.split("_")[1])
        item_name = list(Config.SHOP_ITEMS.keys())[item_index]
        item_data = Config.SHOP_ITEMS[item_name]
        
        user_data = await get_or_create_user(user.id)
        
        if user_data['coins'] < item_data["price"]:
            await query.edit_message_text(
                f"❌ **عذراً!**\n\nليس لديك عملات كافية لشراء {item_name}\n\n"
                f"💰 **المطلوب:** {format_number(item_data['price'])} عملة\n"
                f"💰 **رصيدك:** {format_number(user_data['coins'])} عملة",
                parse_mode='Markdown'
            )
            return
        
        # Deduct coins
        new_coins = user_data['coins'] - item_data["price"]
        supabase.table('users').update({
            'coins': new_coins
        }).eq('user_id', user.id).execute()
        
        # Log purchase
        await log_transaction(user.id, "purchase", -item_data["price"], f"Bought {item_name}")
        
        # Add item to user inventory (if needed)
        # This would require an inventory table
        
        success_text = f"""
✅ **تم الشراء بنجاح!**

🛍️ **العنصر:** {item_name}
💰 **السعر:** {format_number(item_data['price'])} عملة
💰 **الرصيد المتبقي:** {format_number(new_coins)} عملة

🎉 **استمتع بمشترياتك!**
"""
        
        keyboard = [
            [InlineKeyboardButton("🛒 العودة للمتجر", callback_data="shop")],
            [InlineKeyboardButton("📊 ملفي الشخصي", callback_data="profile")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in shop purchase: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء الشراء!")

async def handle_rank_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Handle rank upgrades"""
    query = update.callback_query
    user = query.from_user
    
    try:
        rank = callback_data.split("_")[1].upper()
        price = Config.RANK_PRICES[rank]
        
        user_data = await get_or_create_user(user.id)
        
        if user_data['coins'] < price:
            await query.edit_message_text(
                f"❌ **عذراً!**\n\nليس لديك عملات كافية للترقية إلى {rank}\n\n"
                f"💰 **المطلوب:** {format_number(price)} عملة\n"
                f"💰 **رصيدك:** {format_number(user_data['coins'])} عملة",
                parse_mode='Markdown'
            )
            return
        
        # Deduct coins and upgrade rank
        new_coins = user_data['coins'] - price
        supabase.table('users').update({
            'coins': new_coins,
            'rank': rank
        }).eq('user_id', user.id).execute()
        
        # Log transaction
        await log_transaction(user.id, "rank_upgrade", -price, f"Upgraded to {rank}")
        
        success_text = f"""
🎉 **تهانينا!**

{get_rank_emoji(rank)} **تمت ترقيتك إلى رتبة {rank}!**

💰 **التكلفة:** {format_number(price)} عملة
💰 **الرصيد المتبقي:** {format_number(new_coins)} عملة

⭐ **استمتع بالميزات الجديدة!**
"""
        
        keyboard = [
            [InlineKeyboardButton("📊 ملفي الشخصي", callback_data="profile")],
            [InlineKeyboardButton("🛒 المتجر", callback_data="shop")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in rank upgrade: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء الترقية!")

# Create application globally
application = Application.builder().token(Config.BOT_TOKEN).build()

# Add handlers
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Callback query handler
application.add_handler(CallbackQueryHandler(handle_callback_query))

# Set up webhook
webhook_url = os.environ.get("WEBHOOK_URL")
if webhook_url:
    application.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to {webhook_url}")
else:
    print("WEBHOOK_URL environment variable not set. Bot will not run in webhook mode.")
async def webhook_handler(request: Request):
    await application.update_queue.put(Update.de_json(await request.json(), application.bot))
    return Response("OK", status_code=200)


@app.post("/")
async def telegram_webhook(request: Request):
    return await webhook_handler(request)


@app.get("/")
async def index():
    return "Hello from your Telegram bot!"