import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import logging
import os
import pymongo
from urllib.parse import urlparse

# constants
MESSAGE_START_CONFIRMED = 'Okay. Asking feedback from <@{}> to <@{}>.'
MESSAGE_WRONG_FORMAT = 'Wrong usage of command.'
MESSAGE_NOT_A_COMMAND_ADMIN = 'Sorry, I can\'t recognize that command.'
MESSAGE_NOT_A_COMMAND_NOTADMIN = 'Hi! There is no feedback session currently, we will let you know when it is.'
MESSAGE_START_USAGE = 'Try `start @giver @receiver`!'
MESSAGE_ASK_FOR_FEEDBACK = ('Hi! It\'s feedback time! Please write your feedback to <@{}>! '
                            'Be specific, extended and give your feedback on behavior. '
                            'And don\'t forget to give more positive feedback than negative!')
MESSAGE_FEEDBACK_CONFIRMED = 'You\'ve given <@{}> the following feedback: {}. Thank you!'
MESSAGE_GOT_FEEDBACK = 'You got the following feedback from <@{}>: {}'
LOG_GOT_MESSAGE = 'Got message from user {}: {}'
LOG_SENDING_MESSAGE = 'Sending message to user {}: {}'
ENVVAR_TOKEN = 'FEEDBACKBOT_TOKEN'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('feedbackbot')

class MemberNotFound(Exception):
    pass


# global variables
client = Bot(description="feedbackbot by Sly (test version)",
             command_prefix="", pm_help=False)

mongodb_uri = os.environ.get('MONGODB_URI')
try:
    conn = pymongo.MongoClient(mongodb_uri)
    logger.info('Database connection successful.')
except pymongo.errors.ConnectionFailure as e:
    logger.error('Could not connect to MongoDB: {}'.format(e))

db = conn[urlparse(mongodb_uri).path[1:]]



def is_admin(user_id):
    """Checks whether the giver user is in the 'admins' role in any of the servers the bot is connected to."""
    for server in client.servers:
        for member in server.members:
            if member.id == user_id:
                for role in member.roles:
                    if role.name == 'admins':
                        return True
                return False
    return False


def get_member_by_username(username_string):
    """Returns the Member object if it's found on any of the servers the bot is connected to.
    Otherwise, raises an exception."""

    # username and discriminator like @szilveszter.erdos#7945
    elements = username_string.strip('@').split('#')
    username = elements[0]
    if len(elements) > 1:
        discriminator = elements[1]
    else:
        discriminator = ''

    for server in client.servers:
        for member in server.members:
            if member.name == username and member.discriminator == discriminator:
                return member
    raise MemberNotFound('Username `{}` not found.'.format(username))


@client.event
async def on_ready():
    """This is what happens everytime the bot launches. """
    print('Logged in as '+client.user.name+' (ID:'+client.user.id+') | Connected to ' +
          str(len(client.servers))+' servers | Connected to '+str(len(set(client.get_all_members())))+' users')
    print('--------')
    print('Current Discord.py Version: {} | Current Python Version: {}'.format(
        discord.__version__, platform.python_version()))
    print('--------')
    print('Use this link to invite {}:'.format(client.user.name))
    print('https://discordapp.com/oauth2/authorize?client_id={}&scope=bot&permissions=8'.format(client.user.id))

    # This is buggy, let us know if it doesn't work.
    return await client.change_presence(game=discord.Game(name='Feedback game ;)'))


@client.event
async def on_message(message):
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return
    elif is_admin(message.author.id):
        if message.content.startswith('start'):
            msg_elements = message.content.split()
            # because usage is `start @giver @receiver`
            if len(msg_elements) == 3:
                try:
                    giver = get_member_by_username(msg_elements[1])
                    receiver = get_member_by_username(msg_elements[2])
                    msg = MESSAGE_START_CONFIRMED.format(
                        giver.id, receiver.id)

                    # asking for feedback
                    msg2 = MESSAGE_ASK_FOR_FEEDBACK.format(receiver.id)
                    logger.info(LOG_SENDING_MESSAGE.format(giver.name, msg2))
                    await client.send_message(giver, msg2)
                    db['members-asked'].update_one(
                        {'id': giver.id},
                        {
                            '$set': {
                                'receiver_id': receiver.id,
                                'receiver_name': receiver.name
                            }
                        },
                        upsert=True
                    )

                except MemberNotFound as e:
                    msg = str(e)
            else:
                msg = MESSAGE_WRONG_FORMAT + ' ' + MESSAGE_START_USAGE
        else:
            msg = MESSAGE_NOT_A_COMMAND_ADMIN + ' ' + MESSAGE_START_USAGE
    else:
        giver = message.author
        giver_details = db['members-asked'].find_one({'id': giver.id})
        if giver_details is not None:
            receiver_id = giver_details['receiver_id']
            receiver_name = giver_details['receiver_name']
            db['feedbacks'].update_one(
                {'id': receiver_id},
                {
                    '$push': {
                        'feedback': {
                            'giver': giver.id,
                            'message': message.content
                        }
                    }
                },
                upsert=True
            )

            msg = MESSAGE_FEEDBACK_CONFIRMED.format(receiver_id, message.content)
            msg2 = MESSAGE_GOT_FEEDBACK.format(giver.id, db['feedbacks'].find_one({'id': receiver_id})['feedback'][0]['message'])
            logger.info(LOG_SENDING_MESSAGE.format(receiver_name, msg2))
            await client.send_message(await client.get_user_info(receiver_id), msg2)
            db['members-asked'].remove({'id': giver.id})
        else:
            msg = MESSAGE_NOT_A_COMMAND_NOTADMIN
    logger.info(LOG_GOT_MESSAGE.format(message.channel.user.name, message.content))
    logger.info(LOG_SENDING_MESSAGE.format(message.channel.user.name, msg))
    await client.send_message(message.channel, msg)


if __name__ == '__main__':
    if ENVVAR_TOKEN in os.environ:
        token = os.environ.get(ENVVAR_TOKEN)
        client.run(token)
    else:
        print("Please define an environment variable named {} and put the secret token into it!".format(ENVVAR_TOKEN))