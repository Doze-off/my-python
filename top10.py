import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import datetime

# Configuração de log para arquivo separado
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[logging.FileHandler('top10.txt', 'a', 'utf-8')]  # Salvando logs no arquivo log.txt
)
logger = logging.getLogger(__name__)

# Variáveis globais
db_connection = None
cursor = None

# Função para conectar ao banco de dados
def connect_db():
    global db_connection, cursor
    db_connection = sqlite3.connect('top10.db')  # O banco de dados será salvo no mesmo diretório do script
    cursor = db_connection.cursor()
    # Criar as tabelas se não existirem
    cursor.execute('''CREATE TABLE IF NOT EXISTS message_counts (
                        group_id INTEGER,
                        user_id INTEGER,
                        message_count INTEGER,
                        PRIMARY KEY(group_id, user_id))''')
    db_connection.commit()
    logger.debug("Banco de dados conectado e tabelas criadas.")

# Função para salvar a contagem de mensagens
def save_message_count(group_id, user_id, count):
    cursor.execute('''INSERT OR REPLACE INTO message_counts (group_id, user_id, message_count)
                      VALUES (?, ?, ?)''', (group_id, user_id, count))
    db_connection.commit()
    logger.debug(f"Contagem de mensagens salva para o grupo {group_id}, usuário {user_id}: {count}")

# Função para carregar as contagens de mensagens
def load_message_counts(group_id):
    cursor.execute('''SELECT user_id, message_count FROM message_counts WHERE group_id = ?''', (group_id,))
    return cursor.fetchall()

# Função /start com botão de convite
async def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    group_id = update.message.chat.id
    
    # Criar o botão para convidar para o grupo
    invite_button = InlineKeyboardButton("Adicionar Bot ao seu Grupo", url="https://t.me/Top10_papacu_bot?startgroup=true")
    keyboard = InlineKeyboardMarkup([[invite_button]])

    # Enviar a mensagem com o botão
    await context.bot.send_message(
        chat_id=group_id, 
        text="Olá! Clique no botão abaixo para adicionar o bot ao seu grupo:",
        reply_markup=keyboard
    )
    logger.debug(f"Mensagem de convite enviada para o grupo {group_id}.")

# Função para contar mensagens
async def count_messages(update: Update, context: CallbackContext):
    user = update.message.from_user
    group_id = update.message.chat.id

    cursor.execute('''SELECT message_count FROM message_counts WHERE group_id = ? AND user_id = ?''', (group_id, user.id))
    result = cursor.fetchone()

    if result:
        count = result[0] + 1
    else:
        count = 1

    save_message_count(group_id, user.id, count)

# Função /top10
async def top10(update: Update, context: CallbackContext):
    group_id = update.message.chat.id

    message_counts = load_message_counts(group_id)
    if not message_counts:
        await update.message.reply_text("Ainda não há dados suficientes.")
        return

    # Ordena membros por número de mensagens
    sorted_members = sorted(message_counts, key=lambda x: x[1], reverse=True)
    top_members = sorted_members[:10]
    
    # Exibe os 10 melhores
    text = "Top 10 membros da semana:\n"
    for idx, (user_id, count) in enumerate(top_members, 1):
        user = await context.bot.get_chat_member(group_id, user_id)
        text += f"{idx}. {user.user.first_name}: {count} mensagens\n"
    
    await update.message.reply_text(text)

# Função para enviar relatório no final de semana
async def send_weekly_report(context: CallbackContext):
    # Aqui, pegamos todos os grupos que têm dados
    cursor.execute('''SELECT DISTINCT group_id FROM message_counts''')
    group_ids = cursor.fetchall()

    for group_id_tuple in group_ids:
        group_id = group_id_tuple[0]
        message_counts = load_message_counts(group_id)
        if not message_counts:
            continue

        # Ordena membros por número de mensagens
        sorted_members = sorted(message_counts, key=lambda x: x[1], reverse=True)
        top_members = sorted_members[:10]

        # Exibe os 10 melhores
        text = "Top 10 membros da semana(de mensagem):\n"
        for idx, (user_id, count) in enumerate(top_members, 1):
            user = await context.bot.get_chat_member(group_id, user_id)
            text += f"{idx}. {user.user.first_name}: {count} mensagens\n"
        
        # Envia o relatório
        await context.bot.send_message(chat_id=group_id, text=text)
        logger.debug(f"Relatório semanal enviado para o grupo {group_id}.")

# Função principal
def main():
    connect_db()
    application = Application.builder().token("7671163793:AAGvtyPXFPUp9CbwchBMmdbwecVGi1WpwtI").build()
    
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, count_messages))
    application.add_handler(CommandHandler("top10", top10))
    
    # Agendar envio semanal de relatório (uma vez por semana, por exemplo no domingo)
    job_queue = application.job_queue
    job_queue.run_daily(send_weekly_report, time=datetime.time(hour=10, minute=0))  # Envia às 10:00 AM todo domingo
    
    application.run_polling()

if __name__ == '__main__':
    main()
