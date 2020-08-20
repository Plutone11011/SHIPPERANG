import logging
import os
import json
import math
import random
import schedule
import time
import threading
import redis
from telegram.ext import Updater, CommandHandler, CallbackContext, Filters
from telegram import Update
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

TOKEN = os.getenv('TELEGRAM_TOKEN')

logging.info(os.environ.get('TELEGRAM_TOKEN'))

deadline = datetime(datetime.today().year, datetime.today().month, datetime.today().day, hour=2)
VICTORY = 30
victory_text = ''
redis_server = redis.from_url(os.getenv('REDIS_URL'))
PORT = int(os.environ.get('PORT', 5000))


def setup_shippering_db(update: Update, context: CallbackContext):

    if update.effective_chat.type != 'private':

        chat_administrators = context.bot.get_chat_administrators(chat_id=update.effective_chat.id)
        chat_ship = {}
        chat_ship[update.effective_chat.id] = {}
        chat_ship[update.effective_chat.id]['shippable'] = True
        chat_ship[update.effective_chat.id]['user_counters'] = {}
        for chat_member in chat_administrators:
            chat_ship[update.effective_chat.id]['user_counters'][chat_member.user.id] = 0
        chat_ship[update.effective_chat.id]['last_couple'] = []
        # set a single key containing an object like string, if the key doesn't exist already
        redis_server.setnx(str(update.effective_chat.id), json.dumps(chat_ship[update.effective_chat.id]))


def victory(update: Update, context: CallbackContext, winner1, winner2=None):
    first_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                              user_id=winner1).user.first_name
    last_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                             user_id=winner1).user.last_name
    if winner2:
        first_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                  user_id=winner2).user.first_name
        last_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                 user_id=winner2).user.last_name

    text = f'<a href="tg://user?id={winner1}">{first_name1} {last_name1}</a> ' if last_name1 else f'<a href="tg://user?id={winner1}">{first_name1}</a> '
    if winner2:
        text += f'e <a href="tg://user?id={winner2}">{first_name2} {last_name2}</a> hanno raggiunto {VICTORY} ship. \nCongratulazioni 👋' \
            if last_name2 else f'e <a href="tg://user?id={winner2}">{first_name2}</a>' \
                                f'hanno raggiunto {VICTORY} ship. \nCongratulazioni 👋'
    else:
        text += f'ha raggiunto {VICTORY} ship. \nCongratulazioni 👋'

    text += 'Se vuoi ricominciare usa /reset'

    return text


def start(update: Update, context: CallbackContext):

    setup_shippering_db(update, context)

    schedule.every().day.at("02:00").do(callback_shipping, update.effective_chat.id)
    run_continuously()

    text = '😄 Hello! SHIPPERANG is a bot that will choose a couple of the day in your chat.\n\n ' \
           'Use /help for more info.'
    context.bot.send_message(chat_id=update.effective_chat.id, text=text)


def help(update: Update, context: CallbackContext):
    text = '💕 SHIPPERANG is a bot that will choose a couple of the day in your chat. ' \
           'Everyone who writes a message in your chat will be added to the list of candidates ' \
           'for a couple of the day. Add this bot to your chat ' \
           'and wait for it to gather enough candidates before sending shipping command.\n' \
           '/help: this message\n' \
           '/shipping: picks a couple of the day\n' \
           '/top: ship ranking\n' \
           '/last: last couples picked\n' \
           '/reset: delete every couple'
    context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')


def shipping(update: Update, context: CallbackContext):
    global victory_text

    setup_shippering_db(update, context)

    counters = redis_server.get(str(update.effective_chat.id))
    counters = json.loads(counters)

    if counters['shippable']:
        # last key is not counted for randomization since it's the last ship
        ship1, ship2 = tuple(
            random.sample(range(0, len(counters['user_counters'].keys())), k=2))

        # find the id whose index in the key list is the rng number
        user_id_shipped1 = list(counters['user_counters'].items())[ship1][0]
        user_id_shipped2 = list(counters['user_counters'].items())[ship2][0]

        counters['user_counters'][user_id_shipped1] += 1
        counters['user_counters'][user_id_shipped2] += 1
        counters['last_couple'].append(user_id_shipped1)
        counters['last_couple'].append(user_id_shipped2)
        if len(counters['last_couple']) > 10:
            counters['last_couple'].pop(0)
            counters['last_couple'].pop(0)
        # if someone reached 30, winner
        winners = []
        if counters['user_counters'][user_id_shipped1] >= VICTORY:
            winners.append(user_id_shipped1)
        if counters['user_counters'][user_id_shipped2] >= VICTORY:
            winners.append(user_id_shipped2)
        if len(winners) > 0:
            victory_text = victory(update, context, *winners)



    else:
        # if the ship for today is picked, only need to pop from the stack
        user_id_shipped2 = counters['last_couple'][-1]
        user_id_shipped1 = counters['last_couple'][-2]

    # find out how much needs to be waited to ship again
    now = datetime.today()
    time_to_wait = deadline - now
    total_seconds = time_to_wait.seconds + math.floor(round(time_to_wait.microseconds / 1000000, 1))
    hours, remaining_seconds = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remaining_seconds, 60)

    first_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                              user_id=user_id_shipped1).user.first_name
    last_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                             user_id=user_id_shipped1).user.last_name
    first_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                              user_id=user_id_shipped2).user.first_name
    last_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                           user_id=user_id_shipped2).user.last_name
    text = ''
    if victory_text:
        text += victory_text + '\n\n'
    text += 'La coppia del giorno:\n\n' if counters['shippable'] else 'La coppia del giorno è già stata scelta:\n\n'
    text += f'<a href="tg://user?id={user_id_shipped1}">{first_name1} {last_name1}</a> ' if last_name1 else f'<a href="tg://user?id={user_id_shipped1}">{first_name1}</a>'
    text += f'+ <a href="tg://user?id={user_id_shipped2}">{first_name2} {last_name2}</a> = ❤\n' if last_name2 else f'+ <a href="tg://user?id={user_id_shipped2}">{first_name2}</a> = ❤\n'
    text += f'La nuova coppia del giorno potrà essere scelta tra {hours} ore, {minutes} minuti e {seconds} secondi'

    counters['shippable'] = False
    # write updates
    redis_server.set(str(update.effective_chat.id), json.dumps(counters))
    context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')


def last_ship(update: Update, context: CallbackContext):
    setup_shippering_db(update, context)

    text = 'Le coppie scelte negli ultimi giorni:\n\n'

    counters = redis_server.get(str(update.effective_chat.id))
    counters = json.loads(counters)

    last_couple_stack = counters['last_couple']
    for i in range(0, len(counters['last_couple']), 2):
        user_id_shipped2 = last_couple_stack.pop()
        user_id_shipped1 = last_couple_stack.pop()
        first_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                  user_id=user_id_shipped1).user.first_name
        last_name1 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                 user_id=user_id_shipped1).user.last_name
        first_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                  user_id=user_id_shipped2).user.first_name
        last_name2 = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                 user_id=user_id_shipped2).user.last_name
        text += '❤ = '
        text += f'{first_name1} {last_name1} + ' if last_name1 else f'{first_name1} + '
        text += f'{first_name2} {last_name2}\n' if last_name2 else f'{first_name2}\n'

    context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')


def top_ship(update: Update, context: CallbackContext):
    setup_shippering_db(update, context)

    text = 'Top lovers (coloro scelti il maggior numero di volte):\n\n'

    counters = redis_server.get(str(update.effective_chat.id))
    counters = json.loads(counters)

    id_items = list(counters['user_counters'].items())
    ranking = sorted(id_items, key=lambda id_counter : id_counter[1], reverse=True)
    i = 1
    for rank in ranking:
        first_name = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                  user_id=rank[0]).user.first_name
        last_name = context.bot.get_chat_member(chat_id=update.effective_chat.id,
                                                 user_id=rank[0]).user.last_name
        text += f'{i}. '
        text += f'{first_name} {last_name} — <b>{rank[1]}</b>\n' if last_name else f'{first_name} — <b>{rank[1]}</b>\n'
        i += 1
    context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='HTML')


def restart_counter(update: Update):
    counters = redis_server.get(str(update.effective_chat.id))
    counters = json.loads(counters)

    for user_id in counters['user_counters']:
        counters['user_counters'][user_id] = 0
    counters['last_couple'] = []
    counters['shippable'] = True

    redis_server.set(str(update.effective_chat.id), json.dumps(counters))


def reset(update: Update, context: CallbackContext):
    setup_shippering_db(update, context)

    restart_counter(update)
    context.bot.send_message(chat_id=update.effective_chat.id, text='Reset completato', parse_mode='HTML')


def callback_shipping(chat_id):
    global deadline
    deadline += timedelta(days=1)

    logging.info("CALLBACK TIMER")
    logging.info(deadline)
    counters = redis_server.get(str(chat_id))
    counters = json.loads(counters)

    counters['shippable'] = True
    redis_server.set(str(chat_id), json.dumps(counters))


def run_continuously(interval=5):
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    logging.info("THREAD RUNNING")
    return cease_continuous_run


def main():

    updater = Updater(token=TOKEN, use_context=True)

    dispatcher = updater.dispatcher
    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', help)
    ship_handler = CommandHandler('shipping', shipping, Filters.group)
    last_ship_handler = CommandHandler('last', last_ship, Filters.group)
    top_ship_handler = CommandHandler('top', top_ship, Filters.group)
    reset_handler = CommandHandler('reset', reset, Filters.group)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(ship_handler)
    dispatcher.add_handler(last_ship_handler)
    dispatcher.add_handler(top_ship_handler)
    dispatcher.add_handler(reset_handler)

    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TOKEN)
    updater.bot.setWebhook('https://shipperang.herokuapp.com/' + TOKEN)

    updater.idle()


if __name__ == '__main__':
    main()