import os, uuid, pytz, datetime as dt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Chat
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==============================================
# 🔑 ตั้งค่า TOKEN และ TIMEZONE
# ==============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = pytz.timezone("Asia/Bangkok")

# กลุ่มที่บอทรู้จัก (จะอัปเดตอัตโนมัติ)
KNOWN_GROUPS = {}

app = Application.builder().token(BOT_TOKEN).build()
scheduler = AsyncIOScheduler(timezone=TZ)
scheduler.start()

POSTS = {}

# ==============================================
# 🧱 Helper UI
# ==============================================
def day_buttons():
    days = ["ทุกวัน", "จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    rows = [[InlineKeyboardButton(d, callback_data=f"day::{d}")] for d in days]
    rows.append([InlineKeyboardButton("✅ เสร็จแล้ว เลือกเวลา", callback_data="next::times")])
    return InlineKeyboardMarkup(rows)

def group_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(name, callback_data=f"group::{name}")] for name in KNOWN_GROUPS.keys()]
    )

# ==============================================
# 🚀 เริ่มต้นใช้งาน
# ==============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # 🔹 ถ้าเป็นกลุ่ม
    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        chat_id = chat.id
        chat_title = chat.title
        KNOWN_GROUPS[chat_title] = chat_id
        await update.message.reply_text(
            f"👋 สวัสดีครับ! บอทถูกเพิ่มเข้ากลุ่ม *{chat_title}*\n\n"
            f"ต้องการให้กลุ่มนี้ใช้สำหรับตั้งเวลาโพสต์ไหม?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ใช่ บันทึกกลุ่มนี้", callback_data=f"savegroup::{chat_title}")],
                [InlineKeyboardButton("❌ ไม่ใช่", callback_data="ignore")]
            ])
        )
        return

    # 🔹 ถ้าเป็นแชตส่วนตัว
    if not KNOWN_GROUPS:
        await update.message.reply_text("ยังไม่มีกลุ่มที่บอทรู้จักเลย 😅\nเชิญบอทเข้าในกลุ่มก่อน แล้วพิมพ์ /start อีกครั้ง")
        return

    await update.message.reply_text("เลือกกลุ่มที่จะใช้โพสต์ 👇", reply_markup=group_menu())

# ==============================================
# 💾 บันทึกกลุ่มใหม่
# ==============================================
async def save_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    title = q.data.split("::")[1]
    await q.edit_message_text(f"✅ กลุ่ม *{title}* ถูกบันทึกเรียบร้อยแล้ว!", parse_mode="Markdown")

# ==============================================
# ✅ เมื่อเลือกกลุ่มจากเมนู
# ==============================================
async def pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    label = q.data.split("::")[1]
    context.user_data["group"] = label
    await q.edit_message_text(f"✅ เลือกกลุ่ม: {label}\n\nส่งรูปพร้อมข้อความได้เลย 🖼️")

# ==============================================
# 📸 รับรูป
# ==============================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "group" not in context.user_data:
        await update.message.reply_text("⚠️ กรุณาเลือกกลุ่มก่อน (พิมพ์ /start เพื่อเลือกใหม่)")
        return

    photo = update.message.photo[-1].file_id
    caption = update.message.caption or "(ไม่มีข้อความ)"
    context.user_data["new_post"] = {"photo": photo, "caption": caption, "days": [], "times": []}
    await update.message.reply_text("📅 เลือกวันโพสต์:", reply_markup=day_buttons())

# ==============================================
# 🗓️ เลือกวัน
# ==============================================
async def pick_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    day = q.data.split("::")[1]
    if day != "ทุกวัน":
        context.user_data["new_post"]["days"].append(day)
    else:
        context.user_data["new_post"]["days"] = ["ทุกวัน"]
    await q.edit_message_text(
        f"✅ วันที่เลือก: {', '.join(context.user_data['new_post']['days'])}\n\n"
        "ตอนนี้พิมพ์เวลา (หลายเวลาแยกด้วย , ) เช่น:\n09:00, 13:00, 18:00"
    )

# ==============================================
# ⏰ ตั้งเวลาโพสต์
# ==============================================
async def handle_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    times = [t.strip() for t in update.message.text.split(",")]
    post = context.user_data["new_post"]
    post["times"] = times
    group = context.user_data["group"]
    user_id = update.message.from_user.id

    if user_id not in POSTS:
        POSTS[user_id] = []
    POSTS[user_id].append(post)

    for time in times:
        hour, minute = map(int, time.split(":"))
        if "ทุกวัน" in post["days"]:
            scheduler.add_job(send_post, "cron", hour=hour, minute=minute,
                args=[KNOWN_GROUPS[group], post["photo"], post["caption"]])
        else:
            for d in post["days"]:
                dow = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"].index(d)
                scheduler.add_job(send_post, "cron", day_of_week=dow, hour=hour, minute=minute,
                    args=[KNOWN_GROUPS[group], post["photo"], post["caption"]])

    await update.message.reply_text(
        f"✅ ตั้งโพสต์เรียบร้อย!\n"
        f"📅 วัน: {', '.join(post['days'])}\n"
        f"🕐 เวลา: {', '.join(times)}\n"
        f"📍 กลุ่ม: {group}"
    )

# ==============================================
# 🤖 ส่งโพสต์จริง
# ==============================================
async def send_post(chat_id, photo, caption):
    try:
        await app.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
        print(f"✅ ส่งโพสต์สำเร็จที่ {chat_id}")
    except Exception as e:
        print(f"❌ ส่งโพสต์ล้มเหลว: {e}")

# ==============================================
# 🧾 แสดงโพสต์ที่ตั้งไว้
# ==============================================
async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in POSTS or not POSTS[user_id]:
        await update.message.reply_text("ยังไม่มีโพสต์ที่ตั้งไว้ครับ 📭")
        return

    lines = []
    for i, p in enumerate(POSTS[user_id], 1):
        lines.append(
            f"{i}. {p['caption'][:40]}...\n📅 {', '.join(p['days'])}\n🕐 {', '.join(p['times'])}"
        )
    await update.message.reply_text("\n\n".join(lines))

# ==============================================
# 🧩 Handler
# ==============================================
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_posts))
app.add_handler(CallbackQueryHandler(save_group, pattern="^savegroup::"))
app.add_handler(CallbackQueryHandler(pick_group, pattern="^group::"))
app.add_handler(CallbackQueryHandler(pick_day, pattern="^day::"))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_times))

# ==============================================
# 🚀 Run
# ==============================================
if __name__ == "__main__":
    print("🚀 Telegram Scheduler Bot started...")
    app.run_polling()
