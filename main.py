import html
import json
import logging
import re
import sys
import traceback
from datetime import datetime
from os import environ

import pymongo
from bson import ObjectId
from pymongo.errors import PyMongoError
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import PicklePersistence, Application, ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters, CallbackQueryHandler

from models import Shop, Debtor

# Logging ==============================================================================================================
logging.basicConfig(
    format="[%(funcName)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# MongoDB connection ===================================================================================================
myclient = pymongo.MongoClient('mongodb://localhost:27017/')
qarz_daftar_db = myclient['qarz_daftar']
debtors_col = qarz_daftar_db['debtors']
shops_col = qarz_daftar_db['shops']

# Constants for conversation states ====================================================================================
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
 LIST_OF_DEBTORS,
 CHOSE_OPERATION,
 CHOOSE_ACTION,
 SEND_DEBT,
 SEND_PAYMENT) = range(18)

# Regex constants ======================================================================================================
DEBTOR_PHONE_REGEX = '^\+998\d{9}$'
AMOUNT_REGEX = '^\d+$'


# Helper functions =====================================================================================================
def find_debtor_by_phone(shop_id, debtor_phone):
    shop = shops_col.find_one({'_id': shop_id})
    for debtor_dict in shop.get('debtors'):
        if debtor_dict.get('phone') == debtor_phone:
            return debtor_dict.get('debtor_id')
    return None


def get_debtors_list_keyboard(shop_id):
    found_shop = shops_col.find_one({'_id': shop_id})
    if found_shop:
        keyboard = []
        for debtor in found_shop.get('debtors'):
            found_debtor = debtors_col.find_one({'_id': debtor.get('debtor_id')})
            temp_text = "{} - {:,} so'm".format(
                found_debtor.get('name'),
                found_debtor.get('debt_amount'))
            ikb = InlineKeyboardButton(temp_text, callback_data=str(found_debtor.get('_id')))
            keyboard.append([ikb])

        reply_markup = InlineKeyboardMarkup(keyboard)
    else:
        reply_markup = InlineKeyboardMarkup([[]])

    return reply_markup


def get_debtor_info(debtor_id):
    found_debtor = debtors_col.find_one({'_id': debtor_id})
    if found_debtor:
        text = "phone: {}\n" \
               "name: {}\n" \
               "nickname: {}\n" \
               "debt: {:,} so'm" \
            .format(found_debtor.get('phone_number'),
                    found_debtor.get('name'),
                    found_debtor.get('nickname'),
                    found_debtor.get('debt_amount'))
        return text


# Keyboards ============================================================================================================
plus_minus_back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('➕', callback_data='+'),
                                                  InlineKeyboardButton('➖', callback_data='-')],
                                                 [InlineKeyboardButton('🔙', callback_data='back')]])

choose_role_keyboard = ReplyKeyboardMarkup([['🛒 Shop'],
                                            ['👤 Debtor']],
                                           one_time_keyboard=True)

share_phone_number_keyboard = ReplyKeyboardMarkup([[KeyboardButton(text="Share Phone Number 📞", request_contact=True)],
                                                   [KeyboardButton(text="Back 🔙")]],
                                                  resize_keyboard=True,
                                                  one_time_keyboard=True)

shop_menu_keyboard = ReplyKeyboardMarkup([['🔎 Search debtor'], ['➕ Add debtor'], ['📃 List of debtors']],
                                         one_time_keyboard=True)


# Callback Functions ===================================================================================================
# Start ----------------------------------------------------------------------------------------------------------------
async def start(update: Update, _) -> int:
    await update.message.reply_text(
        'Welcome to the "Qarz Daftar" bot. Please choose your role. ⤵',
        reply_markup=choose_role_keyboard
    )
    return SIGN_IN


# Choose Role ----------------------------------------------------------------------------------------------------------
async def choose_role_unknown(update: Update, _) -> int:
    await update.message.reply_text("Please choose a valid option. Debtor or Shop. ⤵")
    return SIGN_IN


async def choose_role_back(update: Update, _) -> int:
    await update.message.reply_text(
        'Please choose your role. ⤵',
        reply_markup=choose_role_keyboard
    )
    return SIGN_IN


async def choose_role_debtor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['user_type'] = 'debtor'

    await update.message.reply_text("Please share your phone number to sign in as a debtor. ⤵",
                                    reply_markup=share_phone_number_keyboard)
    return SIGN_IN_AS_DEBTOR


async def choose_role_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['user_type'] = 'shop'

    await update.message.reply_text("Please share your phone number to sign in as a shop. ⤵",
                                    reply_markup=share_phone_number_keyboard)
    return SIGN_IN_AS_SHOP


#  Choose Role -> Debtor -----------------------------------------------------------------------------------------------
async def handle_debtor_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number

    context.user_data['phone_number'] = phone_number
    await update.message.reply_text(
        f"You have shared your phone number: {phone_number}. You have been signed in as a debtor.")
    return ConversationHandler.END


async def handle_debtor_wrong_phone_number(update: Update, _) -> int:
    await update.message.reply_text('Wrong format.\nPlease share your phone number to sign in as a debtor.')
    return SIGN_IN_AS_DEBTOR


#  Choose Role -> Shop -> Check Phone Number ---------------------------------------------------------------------------
async def handle_shop_wrong_phone_number(update: Update, _) -> int:
    await update.message.reply_text('Wrong format.\nPlease share your phone number to sign in as a shop.')
    return SIGN_IN_AS_SHOP


async def handle_shop_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number
    context.user_data['shop_phone_number'] = phone_number

    try:
        found_shop = shops_col.find_one({'phone_number': phone_number})

        if found_shop is not None:
            context.user_data['shop_id'] = found_shop.get('_id')
            context.user_data['shop_name'] = found_shop.get('name')
            context.user_data['shop_location'] = found_shop.get('location')

            await update.message.reply_text(
                'Welcome, {}!\nPlease choose option ⤵'.format(context.user_data['shop_name']),
                reply_markup=shop_menu_keyboard)
            return SHOP_MENU
        else:
            text = 'Shop not found.\nProcess of adding new shop is started. Type /cancel to cancel the process.'
            await context.bot.send_message(update.effective_chat.id, text)
            await update.message.reply_text('Send shop name ✍')
            return HANDLE_SHOP_NAME

    except PyMongoError as error:
        logger.error('PyMongoError: {}'.format(error))

        await update.message.reply_text('Error. Please contact administrator.')
        return ConversationHandler.END


#  Choose Role -> Shop -> Add New Shop ---------------------------------------------------------------------------------
async def handle_shop_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_name = update.message.text

    context.user_data['shop_name'] = shop_name
    await update.message.reply_text("Send shop's location ✍")
    return HANDLE_SHOP_LOCATION


async def handle_shop_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_location = update.message.text

    context.user_data['shop_location'] = shop_location

    new_shop = Shop(
        context.user_data.get('shop_name'),
        context.user_data.get('shop_location'),
        context.user_data.get('shop_phone_number'),
    )
    result = shops_col.insert_one(new_shop.to_dict())
    if result:
        context.user_data['shop_id'] = result.inserted_id
        await update.message.reply_text("Shop added\n\nSend /shop_menu")
        return SHOP_MENU
    else:
        await update.message.reply_text("Shop NOT added, please type /start and try again")
        return ConversationHandler.END


async def handle_shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get('shop_id'):
        await update.message.reply_text('Menu:', reply_markup=shop_menu_keyboard)
        return SHOP_MENU
    else:
        await update.message.reply_text('Please type /start to sign in as a shop')
        return ConversationHandler.END


async def handle_add_debtor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['chosen_shop_menu'] = 'add_debtor'
    await update.message.reply_text("Please send new debtor's name")
    return NEW_DEBTOR_NAME


async def handle_new_debtor_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_name = update.message.text

    context.user_data['new_debtor_name'] = new_debtor_name
    await update.message.reply_text("Please send new debtor's nickname")
    return NEW_DEBTOR_NICKNAME


async def handle_new_debtor_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_nickname = update.message.text

    context.user_data['new_debtor_nickname'] = new_debtor_nickname
    await update.message.reply_text("Please send new debtor's phone number in format '+998XXXXXXXXX'")
    return NEW_DEBTOR_PHONE


async def handle_new_debtor_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_phone = update.message.text

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
    await update.message.reply_text(
        "Invalid phone number. Please send new debtor's phone number in format '+998XXXXXXXXX'")
    return NEW_DEBTOR_PHONE


async def handle_new_debtor_debt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_debtor_debt_amount = int(update.message.text)

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
        append_debtor_result = shops_col.update_one({'_id': context.user_data.get('shop_id')},
                                                    {'$push': {'debtors': {
                                                        'debtor_id': debtor_insert_result.inserted_id,
                                                        'phone': context.user_data.get('new_debtor_phone')
                                                    }}})
        if append_debtor_result:

            reply_text = 'New debtor added'
        else:

            reply_text = 'Error. New debtor not added'
        reply_markup = ReplyKeyboardMarkup([['Search debtor', 'Add debtor', 'List of debtors']],
                                           one_time_keyboard=True)
        await update.message.reply_text(f'{reply_text}\n\nMenu:', reply_markup=reply_markup)
        return SHOP_MENU


async def handle_new_debtor_wrong_debt_amount(update: Update, _) -> int:
    await update.message.reply_text(
        "Invalid debt amount. Please send new debtor's debt amount. e.g., '10000' for 10.000 sum debt")
    return NEW_DEBTOR_DEBT_AMOUNT


async def handle_search_debtor_by_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['chosen_shop_menu'] = 'search_debtor'
    await update.message.reply_text("Please send debtor's phone number in format '+998XXXXXXXXX'")
    return SEARCH_DEBTOR_BY_PHONE


async def search_debtor_by_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    debtor_phone = update.message.text

    debtor_id = find_debtor_by_phone(context.user_data.get('shop_id'), debtor_phone)
    if debtor_id:
        context.user_data['chosen_debtor_id'] = debtor_id
        text = get_debtor_info(debtor_id)
        await update.message.reply_text(text, reply_markup=plus_minus_back_keyboard)
        return CHOOSE_ACTION
    else:
        await update.message.reply_text("Debtor not found.\n"
                                        "Please send debtor's phone number in format '+998XXXXXXXXX'")
        return SEARCH_DEBTOR_BY_PHONE


async def search_debtor_by_wrong_phone(update: Update, _) -> int:
    await update.message.reply_text("Invalid phone number. Please send debtor's phone number in format '+998XXXXXXXXX'")
    return SEARCH_DEBTOR_BY_PHONE


async def list_of_debtors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['chosen_shop_menu'] = 'list_of_debtors'
    reply_markup = get_debtors_list_keyboard(context.user_data.get('shop_id'))
    await update.message.reply_text('List of debtors:', reply_markup=reply_markup)

    return LIST_OF_DEBTORS


async def choose_debtor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    debtor_id = ObjectId(query.data)
    context.user_data['chosen_debtor_id'] = debtor_id

    text = get_debtor_info(debtor_id)

    await query.edit_message_text(text, reply_markup=plus_minus_back_keyboard)
    return CHOSE_OPERATION


async def choose_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == '+':
        text = "please send the amount of debt. e.g., '10000' for 10.000 sum debt"
        await query.edit_message_text(text)
        return SEND_DEBT
    elif query.data == '-':
        text = "please send the payment amount. e.g., '10000' for 10.000 sum debt"
        await query.edit_message_text(text)
        return SEND_PAYMENT
    elif query.data == 'back':
        if context.user_data['chosen_shop_menu'] == 'search_debtor':
            await query.edit_message_text("Please send debtor's phone number in format '+998XXXXXXXXX'")
            return SEARCH_DEBTOR_BY_PHONE
        elif context.user_data['chosen_shop_menu'] == 'list_of_debtors':
            reply_markup = get_debtors_list_keyboard(context.user_data.get('shop_id'))
            await query.edit_message_text('List of debtors:', reply_markup=reply_markup)
            return LIST_OF_DEBTORS
        else:
            ...
    else:
        await update.message.reply_text('error, please contact admin')
        return ConversationHandler.END


async def handle_debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    debt_amount = int(update.message.text)
    debtor_id = context.user_data['chosen_debtor_id']

    transaction = {
        'type': 'debt',
        'amount': debt_amount,
        'timestamp': datetime.now()
    }

    push_transaction_result = debtors_col.update_one(
        {"_id": debtor_id},
        {"$push": {"transactions": transaction}}
    )

    inc_debt_result = debtors_col.update_one(
        {"_id": debtor_id},
        {"$inc": {"debt_amount": debt_amount}}
    )
    logger.info('{}\n{}'.format(push_transaction_result.raw_result, inc_debt_result))

    text = get_debtor_info(debtor_id)
    await update.message.reply_text(text, reply_markup=plus_minus_back_keyboard)
    return CHOSE_OPERATION


async def handle_wrong_debt(update: Update, _) -> int:
    await update.message.reply_text("Wrong format.\nPlease send the amount of debt. e.g., '10000' for 10.000 sum debt")
    return SEND_DEBT


async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payment_amount = int(update.message.text)
    transaction = {
        'type': 'payment',
        'amount': payment_amount,
        'timestamp': datetime.now()
    }

    debtor_id = context.user_data['chosen_debtor_id']

    push_transaction_result = debtors_col.update_one(
        {"_id": debtor_id},
        {"$push": {"transactions": transaction}}
    )

    inc_payment_result = debtors_col.update_one(
        {"_id": debtor_id},
        {"$inc": {"debt_amount": -payment_amount}}
    )
    logger.info('{}\n{}'.format(push_transaction_result.raw_result, inc_payment_result))

    text = get_debtor_info(debtor_id)
    await update.message.reply_text(text, reply_markup=plus_minus_back_keyboard)
    return CHOSE_OPERATION


async def handle_wrong_payment(update: Update, _) -> int:
    await update.message.reply_text("Wrong format.\nPlease send the payment amount. e.g., '10000' for 10.000 sum debt")
    return SEND_PAYMENT


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
    if len(message) < 4095:
        await context.bot.send_message(
            chat_id=environ['DEVELOPER_CHAT_ID'], text=message, parse_mode=ParseMode.HTML)
    else:
        await context.bot.send_message(chat_id=environ['DEVELOPER_CHAT_ID'], text=tb_string[:4096])


# Main =================================================================================================================
def main() -> None:
    persistence = PicklePersistence(filepath='persistence.pickle')

    app = Application.builder().token(environ['TOKEN']).persistence(persistence).build()

    main_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      CommandHandler('shop_menu', handle_shop_menu)],
        states={
            # sign in - choose sign in option
            SIGN_IN: [MessageHandler(filters.Regex(re.compile(r'debtor', re.IGNORECASE)), choose_role_debtor),
                      MessageHandler(filters.Regex(re.compile(r'shop', re.IGNORECASE)), choose_role_shop),
                      MessageHandler(filters.ALL & ~filters.COMMAND, choose_role_unknown)],
            # sign in as debtor
            SIGN_IN_AS_DEBTOR: [
                MessageHandler(filters.Regex(re.compile(r'back', re.IGNORECASE)), choose_role_back),
                MessageHandler(filters.CONTACT, handle_debtor_phone_number),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_debtor_wrong_phone_number)],
            # sign in as shop
            SIGN_IN_AS_SHOP: [MessageHandler(filters.Regex(re.compile(r'back', re.IGNORECASE)), choose_role_back),
                              MessageHandler(filters.CONTACT, handle_shop_phone_number),
                              MessageHandler(filters.ALL & ~filters.COMMAND, handle_shop_wrong_phone_number)],
            # shop registration
            HANDLE_SHOP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_name),
                               CommandHandler('cancel', choose_role_shop)],
            HANDLE_SHOP_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_location),
                                   CommandHandler('cancel', choose_role_shop)],
            # shop menu
            SHOP_MENU: [CommandHandler('shop_menu', handle_shop_menu),
                        MessageHandler(filters.Regex('^🔎 Search debtor$'), handle_search_debtor_by_phone),
                        MessageHandler(filters.Regex('^➕ Add debtor$'), handle_add_debtor),
                        MessageHandler(filters.Regex('^📃 List of debtors$'), list_of_debtors)],
            # search for debtor
            SEARCH_DEBTOR_BY_PHONE: [MessageHandler(filters.Regex(DEBTOR_PHONE_REGEX), search_debtor_by_phone),
                                     MessageHandler(filters.ALL & ~filters.COMMAND, search_debtor_by_wrong_phone)],
            CHOOSE_ACTION: [CallbackQueryHandler(choose_operation)],
            # add new debtor
            NEW_DEBTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_name)],
            NEW_DEBTOR_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_nickname)],
            NEW_DEBTOR_PHONE: [MessageHandler(filters.Regex(DEBTOR_PHONE_REGEX), handle_new_debtor_phone),
                               MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_debtor_wrong_phone)],
            NEW_DEBTOR_DEBT_AMOUNT: [MessageHandler(filters.Regex(AMOUNT_REGEX), handle_new_debtor_debt_amount),
                                     MessageHandler(filters.TEXT & ~filters.COMMAND,
                                                    handle_new_debtor_wrong_debt_amount)],
            LIST_OF_DEBTORS: [CallbackQueryHandler(choose_debtor)],
            CHOSE_OPERATION: [CallbackQueryHandler(choose_operation)],
            # + / -
            SEND_DEBT: [MessageHandler(filters.Regex(AMOUNT_REGEX), handle_debt),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wrong_debt)],
            SEND_PAYMENT: [MessageHandler(filters.Regex(AMOUNT_REGEX), handle_payment),
                           MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment)]
        },
        allow_reentry=True,
        fallbacks=[],
        persistent=True,
        name='main_conv'
    )

    app.add_handler(main_conv)

    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)
    # TODO - sign in with password
    # TODO - optimize mongodb search with mongodb indexes


if __name__ == '__main__':
    main()
