import telebot
import time
import schedule
import threading
import logging
import sqlite3
import os

# Configurar o logging para um arquivo separado (log.txt)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('removedor.txt', 'a', 'utf-8')])

# Substitua pelo Token do seu Bot
API_TOKEN = '7604169601:AAHtQXqSUe-QtgF1JksGG2-2gV3h7Jwm6XU'

bot = telebot.TeleBot(API_TOKEN)

# Variáveis globais
grupos_para_limpar = []
intervalo_limpeza = 2 * 60 * 60  # 2 horas por padrão
contas_excluidas_total = 0

# Caminho para o banco de dados SQLite3
DB_PATH = 'removedor.db'

# Função para conectar ao banco de dados SQLite3
def conectar_db():
    conn = sqlite3.connect(DB_PATH)  # Banco de dados persistente no arquivo
    return conn

# Função para criar as tabelas no banco de dados (se ainda não existirem)
def criar_tabelas():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY,
            grupo_id INTEGER UNIQUE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            intervalo_limpeza INTEGER,
            contas_excluidas_total INTEGER
        )
    ''')
    # Insere valores padrão se não existirem
    cursor.execute('''
        INSERT OR IGNORE INTO configuracoes (id, intervalo_limpeza, contas_excluidas_total)
        VALUES (1, ?, ?)
    ''', (intervalo_limpeza, contas_excluidas_total))
    conn.commit()
    conn.close()

# Função para carregar os dados do banco de dados
def carregar_dados():
    global grupos_para_limpar, intervalo_limpeza, contas_excluidas_total
    conn = conectar_db()
    cursor = conn.cursor()

    # Carregar dados dos grupos
    cursor.execute('SELECT grupo_id FROM grupos')
    grupos_para_limpar = [row[0] for row in cursor.fetchall()]

    # Carregar configurações
    cursor.execute('SELECT intervalo_limpeza, contas_excluidas_total FROM configuracoes WHERE id = 1')
    row = cursor.fetchone()
    if row:
        intervalo_limpeza, contas_excluidas_total = row
        logging.debug(f"Dados carregados: Grupos: {grupos_para_limpar}, Intervalo: {intervalo_limpeza}, Contas excluídas: {contas_excluidas_total}")

    conn.close()
    agendar_limpeza()

# Função para salvar dados no banco de dados
def salvar_dados():
    conn = conectar_db()
    cursor = conn.cursor()

    # Atualizar configuração
    cursor.execute('''
        UPDATE configuracoes
        SET intervalo_limpeza = ?, contas_excluidas_total = ?
        WHERE id = 1
    ''', (intervalo_limpeza, contas_excluidas_total))

    # Atualizar lista de grupos
    cursor.execute('DELETE FROM grupos')
    for grupo_id in grupos_para_limpar:
        cursor.execute('INSERT INTO grupos (grupo_id) VALUES (?)', (grupo_id,))

    conn.commit()
    conn.close()

# Função que limpa contas excluídas em um grupo
def limpar_contas_excluidas(chat_id):
    global contas_excluidas_total
    logging.debug(f"Limpando contas excluídas no grupo: {chat_id}")
    try:
        chat_info = bot.get_chat(chat_id)
        if chat_info.type not in ['group', 'supergroup']:
            return

        contas_removidas = 0
        membros = bot.get_chat_administrators(chat_id)
        for membro in membros:
            try:
                bot.get_chat_member(chat_id, membro.user.id)
            except telebot.apihelper.ApiException as e:
                if "USER_ID_INVALID" in str(e):
                    bot.kick_chat_member(chat_id, membro.user.id)
                    contas_removidas += 1
                    contas_excluidas_total += 1

        bot.send_message(chat_id, f"{contas_removidas} contas excluídas removidas!")
    except telebot.apihelper.ApiException as e:
        logging.error(f"Erro na limpeza: {e}")
        bot.send_message(chat_id, f"Ocorreu um erro ao limpar contas: {e}")

# Função que executa a limpeza automática em todos os grupos
def executar_limpeza_automatica():
    global grupos_para_limpar
    if grupos_para_limpar:
        for grupo in grupos_para_limpar:
            limpar_contas_excluidas(grupo)

# Agenda a tarefa de limpeza para executar a cada intervalo_limpeza segundos
def agendar_limpeza():
    # Limpar qualquer tarefa agendada anterior
    schedule.clear()
    schedule.every(intervalo_limpeza).seconds.do(executar_limpeza_automatica)
    logging.debug(f"Limpeza agendada para {intervalo_limpeza} segundos.")

# Função para executar o loop do schedule em uma thread separada
def rodar_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Evento disparado quando o bot é adicionado a um grupo
@bot.message_handler(content_types=['new_chat_members'])
def ao_ser_adicionado(message):
    for membro in message.new_chat_members:
        if membro.id == bot.get_me().id:  # Verifica se o bot foi adicionado
            grupo_id = message.chat.id
            if grupo_id not in grupos_para_limpar:
                grupos_para_limpar.append(grupo_id)
                salvar_dados()  # Salvar após adicionar o grupo
                bot.send_message(
                    grupo_id,
                    "Obrigado por me adicionar como administrador! Este grupo foi incluído automaticamente na lista de limpeza automática."
                )
                logging.debug(f"Grupo {grupo_id} adicionado automaticamente à lista de limpeza.")

# Comando /start para inicializar o bot
@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.type == 'private':
        # Menu inicial para chats privados com botão de adicionar ao grupo
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton(
                text='Adicionar-me a um grupo',
                url='https://t.me/Remove_conta_bot?startgroup=true'
            )
        )
        bot.send_message(
            message.chat.id,
            "Olá! Sou o bot de gerenciamento de grupos. Clique no botão abaixo para me adicionar a um grupo.",
            reply_markup=markup,
        )
    else:
        bot.reply_to(message, "Eu já estou ativo neste grupo!")

# Comando para verificar o status dos grupos
@bot.message_handler(commands=['status'])
def comando_status(message):
    horas = intervalo_limpeza // 3600
    minutos = (intervalo_limpeza % 3600) // 60
    bot.reply_to(
        message,
        f"Intervalo de limpeza automática: {horas} hora(s) e {minutos} minuto(s).\n"
        f"Total de contas excluídas: {contas_excluidas_total}.\n"
        f"Grupos na lista de limpeza: {grupos_para_limpar}."
    )

# Comando para alterar o intervalo de limpeza
@bot.message_handler(commands=['intervalo'])
def comando_definir_intervalo(message):
    if message.chat.type in ['group', 'supergroup']:
        msg = bot.send_message(message.chat.id,
                               "Envie o intervalo de tempo em horas:minutos "
                               "(exemplo: 1:30 para 1 hora e 30 minutos):")
        bot.register_next_step_handler(msg, processar_intervalo)
    else:
        bot.reply_to(message, "Este comando só pode ser usado em grupos ou supergrupos.")

# Processar o novo intervalo de tempo
def processar_intervalo(message):
    global intervalo_limpeza
    try:
        tempo_str = message.text.strip()
        horas, minutos = map(int, tempo_str.split(':'))
        intervalo_limpeza = (horas * 60 + minutos) * 60
        bot.reply_to(
            message,
            f"Intervalo de limpeza automática definido para "
            f"{horas} hora(s) e {minutos} minuto(s)."
        )
        salvar_dados()  # Salvar após alterar o intervalo
        agendar_limpeza()  # Reagendar a limpeza
    except ValueError:
        bot.reply_to(message,
                     "Formato inválido. Por favor, use o formato "
                     "'horas:minutos' (exemplo: 1:30).")

# Comando para executar a limpeza manualmente
@bot.message_handler(commands=['limpar'])
def comando_limpar(message):
    if message.chat.type in ['group', 'supergroup']:
        limpar_contas_excluidas(message.chat.id)
    else:
        bot.reply_to(message, "Este comando só pode ser usado em grupos ou supergrupos.")

# Comando /help para exibir os comandos disponíveis
@bot.message_handler(commands=['help'])
def comando_help(message):
    help_text = (
        "/limpar - Executa a limpeza de contas excluídas no grupo.\n"
        "/intervalo - Define o intervalo de tempo para a limpeza automática (exemplo: 1:30 para 1 hora e 30 minutos).\n"
        "/status - Mostra o intervalo de limpeza automática e o total de contas excluídas no grupo.\n"
    )
    bot.reply_to(message, help_text)

# Iniciar o agendamento da limpeza automática
agendar_limpeza()

# Inicia a thread para o schedule
threading.Thread(target=rodar_schedule, daemon=True).start()

# Criar tabelas e carregar dados ao iniciar
criar_tabelas()
carregar_dados()

# Iniciar o bot
bot.polling()
