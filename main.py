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

from models import Shop
from tests.test_data import fill_shop

logging.basicConfig(
    format="[%(asctime)s %(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('qarz_daftar.log'),
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
 SHOP_DEBTOR_ADD) = range(8)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    reply_markup = ReplyKeyboardMarkup([['Debtor', 'Shop']], one_time_keyboard=True)

    await update.message.reply_text(
        f'Hello {user.first_name}! Welcome to the debtors notepad bot. Please choose your role:',
        reply_markup=reply_markup
    )
    return SIGN_IN


async def choose_role_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please choose a valid option.")
    return SIGN_IN


async def choose_role_debtor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['user_type'] = 'debtor'
    keyboard = [[KeyboardButton(text="Share Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Please share your phone number to sign in as a debtor.",
                                    reply_markup=reply_markup)
    return SIGN_IN_AS_DEBTOR


async def choose_role_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['user_type'] = 'shop'
    keyboard = [[KeyboardButton(text="Share Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Please share your phone number to sign in as a shop.",
                                    reply_markup=reply_markup)
    return SIGN_IN_AS_SHOP


async def handle_debtor_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number
    await update.message.reply_text(
        f"You have shared your phone number: {phone_number}. You have been signed in as a debtor.")
    return ConversationHandler.END


async def handle_debtor_wrong_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Please share your phone number to sign in as a debtor.')
    return SIGN_IN_AS_DEBTOR


async def handle_shop_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.contact.phone_number
    found_shop = shops_col.find_one({'phone_number': phone_number})
    print('shop found: ', found_shop)
    if found_shop:
        print('found shop id', found_shop.get('_id'))
        context.user_data['shop_id'] = found_shop.get('_id')
        await update.message.reply_text('Shop found')
        await handle_shop_menu(update, context)
    else:
        context.user_data['shop_phone_number'] = phone_number
        await update.message.reply_text('Shop not found\n\nSend shop name')
        return HANDLE_SHOP_NAME
    return ConversationHandler.END


async def handle_shop_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_name = update.message.text
    context.user_data['shop_name'] = shop_name
    await update.message.reply_text("Please share shop's location")
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
    print('inserted shop id', result.inserted_id)
    if result:
        context.user_data['shop_id'] = result.inserted_id
        await update.message.reply_text("Shop added\n\nSend /shop_menu")
    else:
        await update.message.reply_text("Shop NOT added")

    return SHOP_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Sign-in process canceled.")
    return ConversationHandler.END


async def handle_shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup([['Search debtor', 'Add debtor']], one_time_keyboard=True)
    await update.message.reply_text('Menu:', reply_markup=reply_markup)
    return SHOP_MENU


async def handle_shop_menu_choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == 'Search debtor':
        await update.message.reply_text("Send debtor's phone number to find.")
        return SHOP_DEBTOR_SEARCH
    elif text == 'Add debtor':
        await update.message.reply_text("Send debtor's phone number to add.")
        return SHOP_DEBTOR_ADD
    else:
        await update.message.reply_text("Please choose a valid option.")
        return SHOP_MENU


async def handle_shop_debtor_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ...


async def handle_shop_debtor_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ...


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
        entry_points=[CommandHandler('start', start_handler)],
        states={
            # sign in - choose sign in option
            SIGN_IN: [MessageHandler(filters.Regex('^Debtor$'), choose_role_debtor),
                      MessageHandler(filters.Regex('^Shop'), choose_role_shop),
                      MessageHandler(filters.ALL & ~filters.COMMAND, choose_role_unknown)],
            # sign in as debtor or shop
            SIGN_IN_AS_DEBTOR: [MessageHandler(filters.CONTACT, handle_debtor_phone_number),
                                MessageHandler(filters.ALL & ~filters.COMMAND, handle_debtor_wrong_phone_number)],

            SIGN_IN_AS_SHOP: [MessageHandler(filters.CONTACT, handle_shop_phone_number)],
            # shop registration
            HANDLE_SHOP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_name)],
            HANDLE_SHOP_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_location)],
            #
            SHOP_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_menu_choose)],
            SHOP_DEBTOR_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_debtor_find)],
            SHOP_DEBTOR_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shop_debtor_add)]
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
