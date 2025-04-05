import re
import datetime
import requests
from collections import defaultdict
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
import os

HF_TOKEN = os.getenv("HF_API_KEY")
HF_MODEL_URL = "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

relatorio = defaultdict(lambda: {'ordens': 0, 'orcamentos': 0, 'garantias': 0, 'reagendamentos': 0})
mensagens_processadas = []

def analisar_com_huggingface(texto):
    prompt = (
        """Leia o texto abaixo e diga se ele contém, de forma clara e direta:
- Perda de garantia
- Aprovação de orçamento
- Reagendamento

Apenas responda 'sim' para cada item se o texto AFIRMAR com clareza. Caso não haja menção clara, responda 'não'.

Responda no formato:
perda: sim/não, orçamento: sim/não, reagendamento: sim/não

Texto:
""" + texto
    )
    print("\n📤 Enviado à IA:\n", prompt)
    try:
        response = requests.post(
            HF_MODEL_URL,
            headers=headers,
            json={"inputs": prompt},
            timeout=60
        )
        result = response.json()
        output = result[0]["generated_text"] if isinstance(result, list) else str(result)
        print("🔍 Análise da IA:", output)
        return output
    except Exception as e:
        print("❌ Erro ao chamar Hugging Face:", e)
        return "erro"

def interpretar_analise(analise, texto):
    texto = texto.lower()
    resposta = analise.lower()
    resultado = {
        'perda_garantia': 'perda: sim' in resposta and 'garantia' in texto,
        'orc_aprovado': 'orçamento: sim' in resposta and ('aprov' in texto or 'orcamento' in texto),
        'reagendamento': 'reagendamento: sim' in resposta and 'reagend' in texto
    }
    print("✔️ Interpretação final:", resultado)
    return resultado

def extrair_dados(mensagem):
    dados = {}
    dados['tecnicos'] = re.findall(r'Tecnico: (.+?)\n', mensagem)
    dados['os'] = re.findall(r'OS:\s+(\d+)', mensagem)
    dados['data'] = re.findall(r'Data:\s+(\d+/\d+/\d+)', mensagem)
    dados['reparo'] = re.findall(r'Reparo:(.+?)\n', mensagem)
    dados['peca'] = re.findall(r'Peça:(.*)', mensagem)

    analise_ia = analisar_com_huggingface(mensagem)
    resultado = interpretar_analise(analise_ia, mensagem)
    dados.update(resultado)
    return dados

async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    mensagens_processadas.append(texto)
    print("\n📥 Mensagem recebida:", texto)
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

    print("🚀 Bot com IA objetiva e regras de segurança iniciado.")
    app.run_polling()
