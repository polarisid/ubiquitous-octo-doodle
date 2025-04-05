import re
import datetime
from collections import defaultdict
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
import os
import openai

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Variáveis globais
relatorio = defaultdict(lambda: {'ordens': 0, 'orcamentos': 0, 'garantias': 0, 'reagendamentos': 0})
mensagens_processadas = []

def analisar_com_chatgpt(texto):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Você é um assistente que analisa relatórios técnicos de atendimento e classifica informações como: orçamento aprovado, reagendamento, perda de garantia."},
                {"role": "user", "content": texto}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erro ao analisar com ChatGPT: {e}"

def extrair_dados(mensagem):
    dados = {}
    dados['tecnicos'] = re.findall(r'Tecnico: (.+?)\n', mensagem)
    dados['os'] = re.findall(r'OS:\s+(\d+)', mensagem)
    dados['data'] = re.findall(r'Data:\s+(\d+/\d+/\d+)', mensagem)
    dados['reparo'] = re.findall(r'Reparo:(.+?)\n', mensagem)
    dados['peca'] = re.findall(r'Peça:(.*)', mensagem)

    analise_ia = analisar_com_chatgpt(mensagem).lower()
    dados['perda_garantia'] = 'garantia' in analise_ia or 'exclusão' in analise_ia
    dados['reagendamento'] = 'reagend' in analise_ia
    dados['orc_aprovado'] = 'aprovad' in analise_ia
    return dados

async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    mensagens_processadas.append(texto)
    dados = extrair_dados(texto)
    tecnicos = dados['tecnicos'][0].split("/") if dados['tecnicos'] else []
    for tecnico in tecnicos:
        tecnico = tecnico.strip()
        relatorio[tecnico]['ordens'] += 1
        if dados['orc_aprovado']:
            relatorio[tecnico]['orcamentos'] += 1
        if dados['perda_garantia']:
            relatorio[tecnico]['garantias'] += 1
        if dados['reagendamento']:
            relatorio[tecnico]['reagendamentos'] += 1

async def gerar_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today().strftime('%d/%m/%Y')
    texto = f"\U0001F4C5 Relatório - {today}\n\n"
    for tecnico, dados in relatorio.items():
        texto += f"👨‍🔧 {tecnico}\n"
        texto += f"• Ordens finalizadas: {dados['ordens']}\n"
        texto += f"• Orçamentos aprovados: {dados['orcamentos']}\n"
        texto += f"• Perdas de garantia: {dados['garantias']}\n"
        texto += f"• Reagendamentos: {dados['reagendamentos']}\n\n"
    await update.message.reply_text(texto)

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), processar_mensagem))
    app.add_handler(CommandHandler("relatorio", gerar_relatorio))

    print("Bot rodando...")
    app.run_polling()
