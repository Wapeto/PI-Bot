import discord
from discord.ext import commands
from discord import app_commands
import datetime
import aiosqlite
import csv
import os

TOKEN = os.environ['TOKEN']

# Enable intents for user interactions
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Create bot instance using Slash Commands
bot = commands.Bot(intents=intents)

DATABASE = "work_sessions.db"

# Create Database Table
async def setup_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS work_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                task TEXT,
                start_time TEXT,
                end_time TEXT,
                duration REAL
            )
        """)
        await db.commit()

# Store active work sessions in memory
active_sessions = {}  # {user_id: (start_time, task)}

# Command to Start Work with Task Name
@bot.slash_command(name="startwork", description="Start tracking your work session.")
async def startwork(ctx, task: str = app_commands.Param(description="What are you working on?")):
    user_id = ctx.author.id

    if user_id in active_sessions:
        await ctx.respond(f"{ctx.author.mention}, you're already tracking a session!", ephemeral=True)
        return

    start_time = datetime.datetime.now()
    active_sessions[user_id] = (start_time, task)

    await ctx.respond(f"⏳ {ctx.author.mention} started working on **{task}** at {start_time.strftime('%H:%M:%S')}.")

# Command to Stop Work
@bot.slash_command(name="stopwork", description="Stop your current work session.")
async def stopwork(ctx):
    user_id = ctx.author.id

    if user_id not in active_sessions:
        await ctx.respond(f"{ctx.author.mention}, you haven't started tracking yet!", ephemeral=True)
        return

    start_time, task = active_sessions.pop(user_id)
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds() / 60  # Convert to minutes

    # Store session in database
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT INTO work_sessions (user_id, username, task, start_time, end_time, duration) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, ctx.author.name, task, start_time.strftime("%Y-%m-%d %H:%M:%S"),
                          end_time.strftime("%Y-%m-%d %H:%M:%S"), duration))
        await db.commit()

    await ctx.respond(f"✅ {ctx.author.mention} stopped working on **{task}**. Duration: {duration:.2f} minutes.")

# Command to Check Active Sessions
@bot.slash_command(name="status", description="See all active work sessions.")
async def status(ctx):
    if not active_sessions:
        await ctx.respond("No active work sessions.", ephemeral=True)
        return

    response = "**Active Work Sessions:**\n"
    for user_id, (start_time, task) in active_sessions.items():
        user = ctx.guild.get_member(user_id)
        response += f"🔹 **{user.name}** - {task} (since {start_time.strftime('%H:%M:%S')})\n"

    await ctx.respond(response)

# Command to Export Data to CSV
@bot.slash_command(name="exportcsv", description="Export work logs as a CSV file.")
async def exportcsv(ctx):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT username, task, start_time, end_time, duration FROM work_sessions")
        logs = await cursor.fetchall()

    if not logs:
        await ctx.respond("No logs available to export.", ephemeral=True)
        return

    filename = "work_sessions.csv"
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["User", "Task", "Start Time", "End Time", "Duration (mins)"])
        writer.writerows(logs)

    await ctx.respond(file=discord.File(filename))

# Run the bot
@bot.event
async def on_ready():
    await setup_db()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
