import html
import json
import logging
import sys
import traceback
from os import environ

import pymongo
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import PicklePersistence, Application, ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters

from models import Shop, Debtor

# from tests.test_data import fill_shop

logging.basicConfig(
    format="[%(funcName)s] %(message)s",
    level=logging.INFO,
    handlers=[
        # logging.FileHandler('qarz_daftar.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

myclient = pymongo.MongoClient('mongodb://localhost:27017/')
qarz_daftar_db = myclient['qarz_daftar']
debtors_col = qarz_daftar_db['debtors']
shops_col = qarz_daftar_db['shops']

# Constants for conversation states
(SIGN_IN,
 SIGN_IN_AS_DEBTOR,
 SIGN_IN_AS_SHOP,
 HANDLE_SHOP_NAME,
 HANDLE_SHOP_LOCATION,
 SHOP_MENU,
 SHOP_DEBTOR_SEARCH,
 SHOP_DEBTOR_ADD,
 NEW_DEBTOR_NAME,
 NEW_DEBTOR_NICKNAME,
 NEW_DEBTOR_PHONE,
 NEW_DEBTOR_DEBT_AMOUNT,
 SEARCH_DEBTOR_BY_PHONE,
 LIST_OF_DEBTORS) = range(14)


def find_debtor_by_phone(shop_id, debtor_phone):
    shop = shops_col.find_one({'_id': shop_id})
    for debtor_dict in shop.get('debtors'):
        if debtor_dict.get('phone') == debtor_phone:
            return debtor_dict.get('debtor_id')
    return None


async def start_handler(update: Update, _) -> int:
    user = update.message.from_user
    reply_markup = ReplyKeyboardMarkup([['Debtor', 'Shop']], one_time_keyboard=True)
    logger.info('/start command from user: {} {}, chat_id: {}'.format(user.first_name,
                                                                      user.last_name,
                                                                      update.effective_chat.id))
    await update.message.reply_text(
        f'Hello {user.first_name}! Welcome to the debtors notepad bot. Please choose your role:',
        reply_markup=reply_markup
    )
    return SIGN_IN


async def choose_role_unknown(update: Update, _) -> int:
    logger.info('invalid role option {}, from user: {} {}, chat_id: {}'.format(update.message.text,
                                                                               update.effective_user.first_name,
                                                                               update.effective_user.last_name,
                                                                               update.effective_chat.id))
    await update.message.reply_text("Please choose a valid option.")
    return SIGN_IN


async def choose_role_debtor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info('Debtor role chosen by user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                                        update.effective_user.last_name,
                                                                        update.effective_chat.id))
    context.user_data['user_type'] = 'debtor'
    keyboard = [[KeyboardButton(text="Share Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Please share your phone number to sign in as a debtor.",
                                    reply_markup=reply_markup)
    return SIGN_IN_AS_DEBTOR


async def handle_debtor_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number
    logger.info(
        'received phone number {} from user: {} {}, chat_id: {}'.format(phone_number,
                                                                        update.effective_user.first_name,
                                                                        update.effective_user.last_name,
                                                                        update.effective_chat.id))
    context.user_data['phone_number'] = phone_number
    await update.message.reply_text(
        f"You have shared your phone number: {phone_number}. You have been signed in as a debtor.")
    return ConversationHandler.END


async def handle_debtor_wrong_phone_number(update: Update, _) -> int:
    logger.info('received invalid phone number {}, from user: {} {}, chat_id: {}'.format(
        update.message.text,
        update.effective_user.first_name,
        update.effective_user.last_name,
        update.effective_chat.id))
    await update.message.reply_text('Please share your phone number to sign in as a debtor.')
    return SIGN_IN_AS_DEBTOR


async def choose_role_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info('Shop role chosen by user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                                      update.effective_user.last_name,
                                                                      update.effective_chat.id))
    context.user_data['user_type'] = 'shop'
    keyboard = [[KeyboardButton(text="Share Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Please share your phone number to sign in as a shop.",
                                    reply_markup=reply_markup)
    return SIGN_IN_AS_SHOP


async def handle_shop_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number
    logger.info(
        'received phone number {} from user: {} {}, chat_id: {}'.format(phone_number,
                                                                        update.effective_user.first_name,
                                                                        update.effective_user.last_name,
                                                                        update.effective_chat.id))
    context.user_data['shop_phone_number'] = phone_number

    found_shop = shops_col.find_one({'phone_number': phone_number})
    logger.info('found shop by phone number: {}'.format(found_shop))
    if found_shop:
        context.user_data['shop_id'] = found_shop.get('_id')
        context.user_data['shop_name'] = found_shop.get('name')
        context.user_data['shop_location'] = found_shop.get('location')
        logger.info('saved user_data: {}'.format(context.user_data))
        await update.message.reply_text('Shop found\n\nSend /shop_menu')
        return SHOP_MENU
    else:
        await update.message.reply_text('Shop not found\n\nSend shop name')
        return HANDLE_SHOP_NAME


async def handle_shop_wrong_phone_number(update: Update, _) -> int:
    logger.info('received invalid phone number {}, from user: {} {}, chat_id: {}'.format(
        update.message.text,
        update.effective_user.first_name,
        update.effective_user.last_name,
        update.effective_chat.id))
    await update.message.reply_text('Please share your phone number to sign in as a shop.')
    return SIGN_IN_AS_SHOP


async def handle_shop_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_name = update.message.text
    logger.info(
        'received shop name {} from user: {} {}, chat_id: {}'.format(shop_name,
                                                                     update.effective_user.first_name,
                                                                     update.effective_user.last_name,
                                                                     update.effective_chat.id))
    context.user_data['shop_name'] = shop_name
    await update.message.reply_text("Please share shop's location")
    return HANDLE_SHOP_LOCATION


async def handle_shop_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_location = update.message.text
    logger.info(
        'received shop location {} from user: {} {}, chat_id: {}'.format(shop_location,
                                                                         update.effective_user.first_name,
                                                                         update.effective_user.last_name,
                                                                         update.effective_chat.id))
    context.user_data['shop_location'] = shop_location
    logger.info('saved user_data: {}'.format(context.user_data))
    new_shop = Shop(
        context.user_data.get('shop_name'),
        context.user_data.get('shop_location'),
        context.user_data.get('shop_phone_number'),
    )
    result = shops_col.insert_one(new_shop.to_dict())
    if result:
        logger.info('inserted shop id {}'.format(result.inserted_id))
        context.user_data['shop_id'] = result.inserted_id
        await update.message.reply_text("Shop added\n\nSend /shop_menu")
        return SHOP_MENU
    else:
        logger.error('Shop NOT added, Shop={}'.format(new_shop))
        await update.message.reply_text("Shop NOT added, please type /start and try again")
        return ConversationHandler.END


async def handle_shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info('/shop_menu command from user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                                          update.effective_user.last_name,
                                                                          update.effective_chat.id))
    if context.user_data.get('shop_id'):
        reply_markup = ReplyKeyboardMarkup([['Search debtor', 'Add debtor', 'List of debtors']],
                                           one_time_keyboard=True)
        await update.message.reply_text('Menu:', reply_markup=reply_markup)
        return SHOP_MENU
    else:
        logger.info('shop_id not assigned, user_data: {}'.format(context.user_data))
        await update.message.reply_text('Please type /start to sign in as a shop')
        return ConversationHandler.END


async def handle_add_debtor(update: Update, _) -> int:
    logger.info('Add debtor message from user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                                          update.effective_user.last_name,
                                                                          update.effective_chat.id))
    await update.message.reply_text("Please send new debtor's name")
    return NEW_DEBTOR_NAME


async def handle_new_debtor_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_name = update.message.text
    logger.info(
        'received new_debtor_name {} from user: {} {}, chat_id: {}'.format(new_debtor_name,
                                                                           update.effective_user.first_name,
                                                                           update.effective_user.last_name,
                                                                           update.effective_chat.id))
    context.user_data['new_debtor_name'] = new_debtor_name
    await update.message.reply_text("Please send new debtor's nickname")
    return NEW_DEBTOR_NICKNAME


async def handle_new_debtor_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_nickname = update.message.text
    logger.info(
        'received new_debtor_nickname {} from user: {} {}, chat_id: {}'.format(new_debtor_nickname,
                                                                               update.effective_user.first_name,
                                                                               update.effective_user.last_name,
                                                                               update.effective_chat.id))
    context.user_data['new_debtor_nickname'] = new_debtor_nickname
    await update.message.reply_text("Please send new debtor's phone number in format '+998XXXXXXXXX'")
    return NEW_DEBTOR_PHONE


async def handle_new_debtor_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_phone = update.message.text
    logger.info(
        'received new_debtor_phone {} from user: {} {}, chat_id: {}'.format(new_debtor_phone,
                                                                            update.effective_user.first_name,
                                                                            update.effective_user.last_name,
                                                                            update.effective_chat.id))
    found_debtor = find_debtor_by_phone(context.user_data.get('shop_id'), new_debtor_phone)
    if found_debtor:
        await update.message.reply_text(
            "Debtor with {} phone number is already exists.\n"
            "Please send new debtor's phone number in format '+998XXXXXXXXX'".format(new_debtor_phone))
        return NEW_DEBTOR_PHONE

    context.user_data['new_debtor_phone'] = new_debtor_phone
    await update.message.reply_text("Please send new debtor's debt amount. e.g., '10000' for 10.000 sum debt")
    return NEW_DEBTOR_DEBT_AMOUNT


async def handle_new_debtor_wrong_phone(update: Update, _) -> int:
    new_debtor_phone = update.message.text
    logger.info(
        'received wrong new_debtor_phone {} from user: {} {}, chat_id: {}'.format(new_debtor_phone,
                                                                                  update.effective_user.first_name,
                                                                                  update.effective_user.last_name,
                                                                                  update.effective_chat.id))
    await update.message.reply_text(
        "Invalid phone number. Please send new debtor's phone number in format '+998XXXXXXXXX'")
    return NEW_DEBTOR_PHONE


async def handle_new_debtor_debt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_debt_amount = int(update.message.text)
    logger.info(
        'received new_debtor_debt_amount {} from user: {} {}, chat_id: {}'.format(new_debtor_debt_amount,
                                                                                  update.effective_user.first_name,
                                                                                  update.effective_user.last_name,
                                                                                  update.effective_chat.id))
    context.user_data['new_debtor_debt_amount'] = new_debtor_debt_amount

    new_debtor = Debtor(
        context.user_data.get('new_debtor_name'),
        context.user_data.get('new_debtor_nickname'),
        context.user_data.get('new_debtor_phone'),
        context.user_data.get('shop_id'),
        context.user_data.get('new_debtor_debt_amount'),
        [],
    )
    debtor_insert_result = debtors_col.insert_one(new_debtor.to_dict())
    if debtor_insert_result:
        logger.info('new debtor inserted id: {}'.format(debtor_insert_result.inserted_id))
        append_debtor_result = shops_col.update_one({'_id': context.user_data.get('shop_id')},
                                                    {'$push': {'debtors': {
                                                        'debtor_id': debtor_insert_result.inserted_id,
                                                        'phone': context.user_data.get('new_debtor_phone')
                                                    }}})
        if append_debtor_result:
            logger.info('new debtor {} appended to {}'.format(debtor_insert_result.inserted_id,
                                                              context.user_data.get('shop_id')))
            reply_text = 'New debtor added'
        else:
            logger.info('Error: new debtor {} not appended to shop {}'.format(debtor_insert_result.inserted_id,
                                                                              context.user_data.get('shop_id')))
            reply_text = 'Error. New debtor not added'
        reply_markup = ReplyKeyboardMarkup([['Search debtor', 'Add debtor', 'List of debtors']],
                                           one_time_keyboard=True)
        await update.message.reply_text(f'{reply_text}\n\nMenu:', reply_markup=reply_markup)
        return SHOP_MENU


async def handle_new_debtor_wrong_debt_amount(update: Update, _) -> int:
    new_debtor_debt_amount = update.message.text
    logger.info(
        'received wrong new_debtor_debt_amount {} from user: {} {}, chat_id: {}'.format(new_debtor_debt_amount,
                                                                                        update.effective_user.first_name,
                                                                                        update.effective_user.last_name,
                                                                                        update.effective_chat.id))
    await update.message.reply_text(
        "Invalid debt amount. Please send new debtor's debt amount. e.g., '10000' for 10.000 sum debt")
    return NEW_DEBTOR_DEBT_AMOUNT


async def handle_search_debtor_by_phone(update: Update, _) -> int:
    logger.info('by phone number message from user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                                               update.effective_user.last_name,
                                                                               update.effective_chat.id))

    await update.message.reply_text("Please send debtor's phone number in format '+998XXXXXXXXX'")
    return SEARCH_DEBTOR_BY_PHONE


async def search_debtor_by_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    debtor_phone = update.message.text
    logger.info('debtor_phone: {} message from user: {} {}, chat_id: {}'.format(debtor_phone,
                                                                                update.effective_user.first_name,
                                                                                update.effective_user.last_name,
                                                                                update.effective_chat.id))
    debtor_id = find_debtor_by_phone(context.user_data.get('shop_id'), debtor_phone)
    if debtor_id:
        debtor = debtors_col.find_one({'_id': debtor_id})
        await update.message.reply_text("phone: {}\nname: {}\nnickname: {}\ndebt: {} sum"
                                        .format(debtor.get('phone_number'),
                                                debtor.get('name'),
                                                debtor.get('nickname'),
                                                debtor.get('debt_amount')))
        # TODO add callback query
    else:
        await update.message.reply_text("debtor not found")
    return SEARCH_DEBTOR_BY_PHONE


async def search_debtor_by_wrong_phone(update: Update, _) -> int:
    debtor_phone = update.message.text
    logger.info('wrong debtor_phone: {} message from user: {} {}, chat_id: {}'.format(debtor_phone,
                                                                                      update.effective_user.first_name,
                                                                                      update.effective_user.last_name,
                                                                                      update.effective_chat.id))

    await update.message.reply_text("Invalid phone number. Please send debtor's phone number in format '+998XXXXXXXXX'")
    return SEARCH_DEBTOR_BY_PHONE


async def list_of_debtors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info('message from user: {} {}, chat_id: {}'.format(update.effective_user.first_name,
                                                               update.effective_user.last_name,
                                                               update.effective_chat.id))
    found_shop = shops_col.find_one({'_id': context.user_data.get('shop_id')})
    if found_shop:
        reply_text = ''
        for debtor in found_shop.get('debtors'):
            found_debtor = debtors_col.find_one({'_id': debtor.get('debtor_id')})
            reply_text += '\n\nphone: {}\nname: {}\nnickname: {}\ndebt: {} sum'.format(
                found_debtor.get('phone_number'),
                found_debtor.get('name'),
                found_debtor.get('nickname'),
                found_debtor.get('debt_amount'))
        # TODO add callback queries
        await update.message.reply_text(reply_text)
    else:
        await update.message.reply_text("shop not found")
    return LIST_OF_DEBTORS


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    await context.bot.send_message(
        chat_id=environ['DEVELOPER_CHAT_ID'], text=message, parse_mode=ParseMode.HTML
    )


def main() -> None:
    # fill_shop(shops_col)
    persistence = PicklePersistence(filepath='persistence.pickle')

    app = Application.builder().token(environ['TOKEN']).persistence(persistence).build()

    main_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start_handler),
                      CommandHandler('shop_menu', handle_shop_menu)],
        states={
            # sign in - choose sign in option
            SIGN_IN: [MessageHandler(filters.Regex('^Debtor$'), choose_role_debtor),
                      MessageHandler(filters.Regex('^Shop'), choose_role_shop),
                      MessageHandler(filters.ALL & ~filters.COMMAND, choose_role_unknown)],
            # sign in as debtor
            SIGN_IN_AS_DEBTOR: [MessageHandler(filters.CONTACT, handle_debtor_phone_number),
                                MessageHandler(filters.ALL & ~filters.COMMAND, handle_debtor_wrong_phone_number)],
            # sign in as shop
            SIGN_IN_AS_SHOP: [MessageHandler(filters.CONTACT, handle_shop_phone_number),
                              MessageHandler(filters.ALL & ~filters.COMMAND, handle_shop_wrong_phone_number)],
            # shop registration
            HANDLE_SHOP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_name)],
            HANDLE_SHOP_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_location)],
            # shop menu
            SHOP_MENU: [CommandHandler('shop_menu', handle_shop_menu),
                        MessageHandler(filters.Regex('^Search debtor$'), handle_search_debtor_by_phone),
                        MessageHandler(filters.Regex('^Add debtor$'), handle_add_debtor),
                        MessageHandler(filters.Regex('^List of debtors$'), list_of_debtors)],
            # search for debtor
            SEARCH_DEBTOR_BY_PHONE: [MessageHandler(filters.Regex('^\+998\d{9}$'), search_debtor_by_phone),
                                     MessageHandler(filters.ALL & ~filters.COMMAND, search_debtor_by_wrong_phone)],
            # add new debtor
            NEW_DEBTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_name)],
            NEW_DEBTOR_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_nickname)],
            NEW_DEBTOR_PHONE: [MessageHandler(filters.Regex('^\+998\d{9}$'), handle_new_debtor_phone),
                               MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_wrong_phone)],
            NEW_DEBTOR_DEBT_AMOUNT: [MessageHandler(filters.Regex('^\d+$'), handle_new_debtor_debt_amount),
                                     MessageHandler(filters.TEXT & ~filters.COMMAND,
                                                    handle_new_debtor_wrong_debt_amount)]
        },
        allow_reentry=True,
        fallbacks=[],
        persistent=True,
        name='main_conv'
    )

    app.add_handler(main_conv)

    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
