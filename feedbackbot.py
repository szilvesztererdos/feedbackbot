import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import logging
import os
import pymongo
from urllib.parse import urlparse
from datetime import datetime

# constants
MESSAGE_START_CONFIRMED = 'Okay. Asking feedback from **{}** to **{}**.'
MESSAGE_WRONG_FORMAT = 'Wrong usage of command.'
MESSAGE_NOT_A_COMMAND_ADMIN = 'Sorry, I can\'t recognize that command.'
MESSAGE_NOT_A_COMMAND_NOTADMIN = '''Hi! There is no feedback session currently, we will let you know when it is.
You can check whether you received any feedback by typing in the `list` command.'''
MESSAGE_ADMIN_USAGE = '''If you want to start a session, type `start @giver @receiver`.
If you want to define new questions, type `questions define`.
If you want to list feedback given to you, type `list`.'''
MESSAGE_ASK_FOR_FEEDBACK = ('Hi! It\'s feedback time! Please write your feedback to **{}**! '
                            'Be specific, extended and give your feedback on behavior. '
                            'And don\'t forget to give more positive feedback than negative!')
MESSAGE_FEEDBACK_CONFIRMED = 'You\'ve given **{}** the following feedback: {}. Thank you!'
MESSAGE_LIST_FEEDBACK = 'You have got the following feedback until now: \n{}'
MESSAGE_NO_FEEDBACK_AVAILABLE = '''Sorry, you haven''t got any feedback until now.
Ask an admin to start a feedback session, so you can got feedback.'''
MESSAGE_DEFINE_QUESTIONS = 'You can add new questions by issuing the `questions` command'
MESSAGE_CURRENT_QUESTIONS = 'These are the questions currently defined: \n{}'
MESSAGE_NO_QUESTIONS = 'There are no questions defined.'
MESSAGE_WANT_NEW_QUESTION = 'Do you want to add a new question? (`yes`/`no`)'
MESSAGE_ADD_NEW_QUESTION = 'Please type in your question.'
MESSAGE_EXIT_DEFINE_QUESTIONS = 'You have chosen to exit adding more questions.'
MESSAGE_DEFINE_QUESTIONS_YESNO = 'Please respond with either `yes` or `no`.'
MESSAGE_NEXT_QUESTION = 'The next question is: '
MESSAGE_WANT_REMOVE_QUESTION = 'Please type in the number of the question you want to remove '
MESSAGE_EXIT_REMOVE_QUESTIONS = 'You have chosen to exit removing more questions. '
MESSAGE_REMOVE_QUESTIONS_ONLY_NUMBERS = 'Please choose from the list of numbers corresponding to the questions '
MESSAGE_REMOVE_QUESTIONS_CANCEL = 'or `cancel` if you want to exit question removal.'
MESSAGE_REMOVAL_SUCCESS = 'Successfully removed question.'
LOG_GOT_MESSAGE = 'Got message from user {}: {}'
LOG_SENDING_MESSAGE = 'Sending message to user {}: {}'
ENVVAR_TOKEN = 'FEEDBACKBOT_TOKEN'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('feedbackbot')


class MemberNotFound(Exception):
    pass


class RoleOrMemberNotFound(Exception):
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


def get_member_or_role(name_string):
    """Returns the member/mention or members of a role/mention in a list on any of the servers 
    the bot is connected to. Otherwise, raises an exception."""
    try:
        member = get_member_by_username(name_string)
        return [member], member.nick
    except MemberNotFound:
        members = []
        name_string = name_string.strip('@')
        for server in client.servers:
            for server_role in server.roles:
                if server_role.name == name_string:
                    # search for all members with that role
                    for member in server.members:
                        for member_role in member.roles:
                            if member_role == server_role:
                                members.append(member)
                                break
                    break
        if members:
            return members, '@' + server_role.name
        else:
            raise RoleOrMemberNotFound('Username or role `{}` not found.'.format(name_string))


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


async def send_msg(user, msg):
    """Sends a message to a user or channel and logs it. """
    logger.info(LOG_SENDING_MESSAGE.format(user, msg))
    await client.send_message(user, msg)


async def process_ask_queue(giver, first_time=False):
    next_to_ask_details = db['ask-queue'].find_one(
            {
                'id': giver.id,
                'status': 'to-ask'
            }
        )
    if next_to_ask_details:
        receiver_id = next_to_ask_details['receiver_id']
        receiver_nick = next_to_ask_details['receiver_nick']
        question_content = next_to_ask_details['question_content']

        if first_time:
            msg = MESSAGE_ASK_FOR_FEEDBACK.format(receiver_nick)
            await send_msg(giver, msg)

        msg = MESSAGE_NEXT_QUESTION + question_content
        await send_msg(giver, msg)

        db['ask-queue'].update(
            {
                'id': giver.id,
                'receiver_id': receiver_id
            },
            {
                '$set': {
                    'status': 'asked'
                }
            }
        )


def push_ask_queue(receiver, giver, question):
    db['ask-queue'].insert(
        {
            'id': giver.id,
            'giver_nick': giver.nick,
            'receiver_id': receiver.id,
            'receiver_nick': receiver.nick,
            'question_content': question['content'],
            'status': 'to-ask'
        }
    )


async def list_questions(message):
    """List questions defined in the database with numbering. """

    if 'questions' in db.collection_names() and db['questions'].count():
        questions_db = list(db['questions'].find({}, {'content': 1}))
        questions_with_index_str = \
            ['{}. {}'.format(i+1, e['content']) for i, e in enumerate(questions_db) if 'content' in e]
        questions_str = '\n'.join(questions_with_index_str)
        msg = MESSAGE_CURRENT_QUESTIONS.format(questions_str)
        await send_msg(message.channel.user, msg)
    else:
        msg = MESSAGE_NO_QUESTIONS


def renumber_questions():
    for counter, question in enumerate(db['questions'].find({})):
        db['questions'].update_one(
            {
                '_id': question['_id']
            },
            {
                '$set': {
                    'index': str(counter + 1)
                }
            },
            upsert=True
        )


async def handle_start_questions_define(message):
    """Handles the `questions` command issued by an admin and starts a conversation
    to add questions. """

    await list_questions(message)

    db['settings'].update_one(
        {
            'status': {
                '$exists': True
            }
        },
        {
            '$set': {
                'status': 'questions-define-pending'
            }
        },
        upsert=True
    )
    msg = MESSAGE_WANT_NEW_QUESTION
    await send_msg(message.channel.user, msg)


async def handle_want_question(message):
    """Handles responding with yes/no while admin in question defining session. """

    if message.content.lower() == 'yes':
        db['settings'].update_one(
            {
                'status': {
                    '$exists': True
                }
            },
            {
                '$set': {
                    'status': 'questions-define-new'
                }
            },
            upsert=True
        )
        msg = MESSAGE_ADD_NEW_QUESTION
        await send_msg(message.channel.user, msg)
    elif message.content.lower() == 'no':
        db['settings'].remove(
            {
                'status': 'questions-define-pending'
            }
        )
        msg = MESSAGE_EXIT_DEFINE_QUESTIONS
        await send_msg(message.channel.user, msg)
    else:
        msg = MESSAGE_DEFINE_QUESTIONS_YESNO
        await send_msg(message.channel.user, msg)


async def handle_add_question(message):
    """Handles adding new question while admin in question defining session. """

    # inserting new question into database
    db['questions'].insert(
        {
            'content': message.content
        }
    )

    renumber_questions()

    # asking whether admin wants new question to add
    db['settings'].update_one(
        {
            'status': {
                '$exists': True
            }
        },
        {
            '$set': {
                'status': 'questions-define-pending'
            }
        },
        upsert=True
    )
    await list_questions(message)
    msg = MESSAGE_WANT_NEW_QUESTION
    await send_msg(message.channel.user, msg)


async def handle_start_question_removal(message):
    """Handles `question remove` command issued by an admin, lists the currently defined questions
    and gives an opportunity to remove from them. """

    await list_questions(message)

    msg = MESSAGE_WANT_REMOVE_QUESTION + MESSAGE_REMOVE_QUESTIONS_CANCEL
    await send_msg(message.channel.user, msg)

    db['settings'].update_one(
        {
            'status': {
                '$exists': True
            }
        },
        {
            '$set': {
                'status': 'questions-remove-pending'
            }
        },
        upsert=True
    )


async def handle_question_remove(message):
    """Handles removing questions while admin in question removal session. """

    if message.content.lower() == 'cancel':
        db['settings'].remove(
            {
                'status': 'questions-remove-pending'
            }
        )
        msg = MESSAGE_EXIT_REMOVE_QUESTIONS
        await send_msg(message.channel.user, msg)
    # we can assume that indexes are continous since we renumber them after each insert/remove with renumber_questions()
    elif message.content in [str(i+1) for i in range(db['questions'].count())]:
        db['questions'].remove(
            {
                'index': message.content
            }
        )
        renumber_questions()
        msg = MESSAGE_REMOVAL_SUCCESS + '\n' + MESSAGE_WANT_REMOVE_QUESTION + MESSAGE_REMOVE_QUESTIONS_CANCEL
        await list_questions(message)
        await send_msg(message.channel.user, msg)
    else:
        msg = MESSAGE_REMOVE_QUESTIONS_ONLY_NUMBERS + MESSAGE_REMOVE_QUESTIONS_CANCEL
        await send_msg(message.channel.user, msg)


async def handle_start(message):
    """Handles the `start @giver @receiver` command issued by an admin and starts a
    feedback session. """

    # if we have questions defined
    if 'questions' in db.collection_names():
        msg_elements = message.content.split()
        # because usage is `start @giver @receiver`
        if len(msg_elements) == 3:
            # get member or role and confirm command
            try:
                givers, giver_mention = get_member_or_role(msg_elements[1])
                receivers, receiver_mention = get_member_or_role(msg_elements[2])
            except RoleOrMemberNotFound as e:
                msg = str(e)
                await send_msg(message.channel.user, msg)
            else:
                msg = MESSAGE_START_CONFIRMED.format(giver_mention, receiver_mention)
                await send_msg(message.channel.user, msg)

                # asking for feedback
                for giver in givers:
                    for receiver in receivers:
                        if receiver is not giver:
                            for question in db['questions'].find({}):
                                push_ask_queue(receiver, giver, question)
                    await process_ask_queue(giver, True)

        else:
            msg = MESSAGE_WRONG_FORMAT + '\n' + MESSAGE_ADMIN_USAGE
            await send_msg(message.channel.user, msg)
    else:
        msg = MESSAGE_NO_QUESTIONS + ' ' + MESSAGE_DEFINE_QUESTIONS
        await send_msg(message.channel.user, msg)

async def handle_list(message):
    """Handles `list` command and lists given feedback messages. """
    feedback_details = db['feedbacks'].find_one({'id': message.author.id})
    if feedback_details is not None:
        question_list = {}
        for feedback in feedback_details['feedback']:
            if feedback['question_content'] not in question_list:
                question_list[feedback['question_content']] = []

            question_list[feedback['question_content']].append(
                '**{}** ({:%Y.%m.%d. %H:%M}): {}'.format(
                    feedback['giver_nick'],
                    feedback['datetime'],
                    feedback['message']
                )
            )

        feedback_list_str = ''
        for question_content, feedback_list in question_list.items():
            feedback_list_str += '\n*' + question_content + '*\n'
            for feedback_str in feedback_list:            
                feedback_list_str += '\t' + feedback_str + '\n'

        msg = MESSAGE_LIST_FEEDBACK.format(feedback_list_str)
    else:
        msg = MESSAGE_NO_FEEDBACK_AVAILABLE
    await send_msg(message.channel.user, msg)


async def handle_send_feedback(message):
    """Handles feedback sent as an answer to the bot's question. """
    ask_details = db['ask-queue'].find_one({'id': message.author.id, 'status': 'asked'})
    giver_nick = ask_details['giver_nick']
    giver = message.author
    receiver_id = ask_details['receiver_id']
    receiver_nick = ask_details['receiver_nick']
    question_content = ask_details['question_content']

    db['feedbacks'].update_one(
        {
            'id': receiver_id,
            'receiver_nick': receiver_nick
        },
        {
            '$push': {
                'feedback': {
                    'giver': giver.id,
                    'giver_nick': giver_nick,
                    'question_content': question_content,
                    'message': message.content,
                    'datetime': datetime.now()
                }
            }
        },
        upsert=True
    )

    # confirm feedback
    msg = MESSAGE_FEEDBACK_CONFIRMED.format(receiver_nick, message.content)
    await send_msg(message.channel.user, msg)

    # remove from queue and continue processing
    db['ask-queue'].remove({'id': giver.id, 'receiver_id': receiver_id, 'question_content': question_content})
    await process_ask_queue(giver)


@client.event
async def on_message(message):
    """This is what happens every time when the bot sees a message. """
    # we do not want the bot to reply to itself
    if message.author == client.user:
        return
    # we do not want the bot to reply not in a pm
    elif message.channel.type.name != 'private':
        return
    # admin starting the session
    elif message.content.startswith('start') and is_admin(message.author.id):
        await handle_start(message)
    # admin starting question defining
    elif message.content.startswith('questions define') and is_admin(message.author.id):
        await handle_start_questions_define(message)
    # admin answering yes/no while defining questions
    elif 'settings' in db.collection_names() and \
            db['settings'].find_one({'status': 'questions-define-pending'}) and \
            is_admin(message.author.id):
        await handle_want_question(message)
    # admin typing in new question
    elif 'settings' in db.collection_names() and \
            db['settings'].find_one({'status': 'questions-define-new'}) and \
            is_admin(message.author.id):
        await handle_add_question(message)
    # admin starting question removal
    elif message.content.startswith('questions remove') and is_admin(message.author.id):
        await handle_start_question_removal(message)
    # admin remove question
    elif 'settings' in db.collection_names() and \
            db['settings'].find_one({'status': 'questions-remove-pending'}) and \
            is_admin(message.author.id):
        await handle_question_remove(message)
    # receiver listing feedback
    elif message.content.startswith('list'):
        await handle_list(message)
    # giver sending a feedback
    elif db['ask-queue'].find_one({'id': message.author.id, 'status': 'asked'}):
        await handle_send_feedback(message)
    # not matching any case
    else:
        if is_admin(message.author.id):
            msg = MESSAGE_NOT_A_COMMAND_ADMIN + '\n' + MESSAGE_ADMIN_USAGE
            await send_msg(message.channel, msg)
        else:
            msg = MESSAGE_NOT_A_COMMAND_NOTADMIN
            await send_msg(message.channel, msg)
    
    try:
        logger.info(LOG_GOT_MESSAGE.format(message.channel.user.name, message.content))
    except AttributeError:
        logger.info(LOG_GOT_MESSAGE.format(message.channel, message.content))


if __name__ == '__main__':
    if ENVVAR_TOKEN in os.environ:
        token = os.environ.get(ENVVAR_TOKEN)
        client.run(token)
    else:
        print("Please define an environment variable named {} and put the secret token into it!".format(ENVVAR_TOKEN))