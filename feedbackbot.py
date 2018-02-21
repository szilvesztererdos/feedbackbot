import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform

# basic info
client = Bot(description="feedbackbot by Sly (test version)", command_prefix="", pm_help = False)

# This is what happens everytime the bot launches.
@client.event
async def on_ready():
	print('Logged in as '+client.user.name+' (ID:'+client.user.id+') | Connected to '+str(len(client.servers))+' servers | Connected to '+str(len(set(client.get_all_members())))+' users')
	print('--------')
	print('Current Discord.py Version: {} | Current Python Version: {}'.format(discord.__version__, platform.python_version()))
	print('--------')
	print('Use this link to invite {}:'.format(client.user.name))
	print('https://discordapp.com/oauth2/authorize?client_id={}&scope=bot&permissions=8'.format(client.user.id))

	return await client.change_presence(game=discord.Game(name='PLAYING STATUS HERE')) #This is buggy, let us know if it doesn't work.

@client.event
async def on_message(message):
	# we do not want the bot to reply to itself
	if message.author == client.user:
		return

	if message.content.startswith('hello'):
		msg = 'Hello {0.author.mention}'.format(message)
	else:
		msg = 'I do not know much yet, sorry :('
	await client.send_message(message.channel, msg)

client.run('NDE0NjY4NzM2MDc1NjYxMzIz.DWquiw.IDGdnR_vw6SYPbPs-7ZBVCk8H7Y')
