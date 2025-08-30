import logging
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update
from telegram.constants import ParseMode
import os
import supabase
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Supabase Client
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase_client = supabase.create_client(SUPABASE_URL, SUPABASE_KEY)

class AdminBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")
        
        self.updater = Updater(self.token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.setup_handlers()

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin from Supabase"""
        try:
            result = supabase_client.table('admins').select('*').eq('telegram_id', user_id).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    def log_admin_action(self, action: str, admin_id: int, details: str = ""):
        """Log admin actions to Supabase"""
        try:
            supabase_client.table('admin_logs').insert({
                'admin_id': admin_id,
                'action': action,
                'details': details,
                'timestamp': datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

    def setup_handlers(self):
        """Setup all admin command handlers"""
        self.dispatcher.add_handler(CommandHandler('rsvps', self.rsvps_command))
        self.dispatcher.add_handler(CommandHandler('approve', self.approve_command))
        self.dispatcher.add_handler(CommandHandler('deny', self.deny_command))
        self.dispatcher.add_handler(CommandHandler('broadcast', self.broadcast_command))
        self.dispatcher.add_handler(CommandHandler('admin', self.admin_panel))

    def rsvps_command(self, update: Update, context: CallbackContext):
        """Handle /rsvps command - show pending RSVPs"""
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ Admin access required.")
            return
        
        try:
            # Get pending RSVPs from Supabase
            result = supabase_client.table('rsvps').select('*, users(*)').eq('status', 'pending').execute()
            pending_rsvps = result.data
            
            if not pending_rsvps:
                update.message.reply_text("✅ No pending RSVPs!")
                return
            
            response = "📋 *Pending RSVPs*\n\n"
            for rsvp in pending_rsvps[:10]:  # Show first 10
                user = rsvp.get('users', {})
                response += f"👤 User: {user.get('name', 'Unknown')}\n"
                response += f"🆔 ID: `{rsvp['user_id']}`\n"
                response += f"📅 Event: {rsvp.get('event_name', 'N/A')}\n"
                response += f"⏰ Submitted: {rsvp.get('created_at', 'N/A')}\n"
                response += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
            self.log_admin_action('viewed_rsvps', update.effective_user.id)
            
        except Exception as e:
            logger.error(f"Error fetching RSVPs: {e}")
            update.message.reply_text("❌ Error fetching RSVPs. Check logs.")

    def approve_command(self, update: Update, context: CallbackContext):
        """Approve RSVP with user ID"""
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            update.message.reply_text("Usage: /approve <user_id>")
            return
        
        user_id = context.args[0]
        try:
            # Update RSVP status in Supabase
            supabase_client.table('rsvps').update({'status': 'approved'}).eq('user_id', user_id).execute()
            
            # Notify user
            user_result = supabase_client.table('users').select('telegram_id').eq('id', user_id).execute()
            if user_result.data:
                telegram_id = user_result.data[0]['telegram_id']
                context.bot.send_message(telegram_id, "🎉 Your RSVP has been approved!")
            
            update.message.reply_text(f"✅ Approved RSVP for user {user_id}")
            self.log_admin_action('approved_rsvp', update.effective_user.id, f"user_id: {user_id}")
            
        except Exception as e:
            logger.error(f"Error approving RSVP: {e}")
            update.message.reply_text("❌ Error approving RSVP.")

    def deny_command(self, update: Update, context: CallbackContext):
        """Deny RSVP with user ID"""
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            update.message.reply_text("Usage: /deny <user_id>")
            return
        
        user_id = context.args[0]
        try:
            # Update RSVP status
            supabase_client.table('rsvps').update({'status': 'denied'}).eq('user_id', user_id).execute()
            
            # Notify user with optional reason
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            user_result = supabase_client.table('users').select('telegram_id').eq('id', user_id).execute()
            if user_result.data:
                telegram_id = user_result.data[0]['telegram_id']
                context.bot.send_message(telegram_id, f"❌ Your RSVP was denied. Reason: {reason}")
            
            update.message.reply_text(f"❌ Denied RSVP for user {user_id}")
            self.log_admin_action('denied_rsvp', update.effective_user.id, f"user_id: {user_id}, reason: {reason}")
            
        except Exception as e:
            logger.error(f"Error denying RSVP: {e}")
            update.message.reply_text("❌ Error denying RSVP.")

    def broadcast_command(self, update: Update, context: CallbackContext):
        """Broadcast message to all users"""
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ Admin access required.")
            return
        
        if not context.args:
            update.message.reply_text("Usage: /broadcast <message>")
            return
        
        message = " ".join(context.args)
        try:
            # Get all users from Supabase
            users_result = supabase_client.table('users').select('telegram_id').execute()
            users = users_result.data
            
            success_count = 0
            for user in users:
                try:
                    context.bot.send_message(user['telegram_id'], f"📢 Announcement:\n\n{message}")
                    success_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to user {user['telegram_id']}: {e}")
            
            update.message.reply_text(f"📢 Broadcast sent to {success_count}/{len(users)} users")
            self.log_admin_action('sent_broadcast', update.effective_user.id, f"reach: {success_count}/{len(users)}")
            
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            update.message.reply_text("❌ Error sending broadcast.")

    def admin_panel(self, update: Update, context: CallbackContext):
        """Show admin panel"""
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ Admin access required.")
            return
        
        panel_text = """
🛠️ *ADMIN PANEL*

• /rsvps — Pending RSVPs
• /approve <userid> — Approve RSVP
• /deny <userid> — Deny RSVP
• /broadcast <text> — DM all users

*Quick Commands:*
/approve 123456789
/deny 123456789 "reason"
/broadcast Important announcement!
        """.strip()
        
        update.message.reply_text(panel_text, parse_mode=ParseMode.MARKDOWN)
        self.log_admin_action('accessed_panel', update.effective_user.id)

    def start(self):
        """Start the bot"""
        self.updater.start_polling()
        logger.info("Admin Bot started!")
        self.updater.idle()

# Main execution
if __name__ == '__main__':
    try:
        bot = AdminBot()
        bot.start()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
