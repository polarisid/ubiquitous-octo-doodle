import re
import json
import datetime
import requests
from collections import defaultdict
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler
import os

ARQUIVO_JSON = "relatorio_dados.json"
TECNICOS_PRINCIPAIS = ["Gabriel", "Carlos", "Breno", "Wesley", "Daniel", "Phablo", "Lazaro"]

HF_TOKEN = os.getenv("HF_API_KEY")
HF_MODEL_URL = "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# Carregar dados salvos
def carregar_relatorio():
    try:
        with open(ARQUIVO_JSON, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_relatorio(data):
    with open(ARQUIVO_JSON, "w") as f:
        json.dump(data, f, indent=2)

relatorio_por_data = carregar_relatorio()

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
    print("\n📥 Mensagem recebida:\n", texto)
    dados = extrair_dados(texto)

    data_msg = dados['data'][0] if dados['data'] else datetime.date.today().strftime('%d/%m/%Y')
    tecnicos_raw = dados['tecnicos'][0] if dados['tecnicos'] else ''
    tecnicos_encontrados = [nome.strip() for nome in tecnicos_raw.split("/") if nome.strip()]
    print("👥 Técnicos identificados:", tecnicos_encontrados)

    tecnico_principal = next((nome for nome in tecnicos_encontrados if nome.lower() in [n.lower() for n in TECNICOS_PRINCIPAIS]), None)
    if not tecnico_principal:
        print("⚠️ Nenhum técnico principal reconhecido.")
        return

    relatorio = relatorio_por_data.setdefault(data_msg, {})
    tecnico_data = relatorio.setdefault(tecnico_principal, {'ordens': 0, 'orcamentos': 0, 'garantias': 0, 'reagendamentos': 0})
    tecnico_data['ordens'] += 1
    if dados['orc_aprovado']:
        tecnico_data['orcamentos'] += 1
    if dados['perda_garantia']:
        tecnico_data['garantias'] += 1
    if dados['reagendamento']:
        tecnico_data['reagendamentos'] += 1

    salvar_relatorio(relatorio_por_data)

async def gerar_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        data = args[0]
    else:
        data = datetime.date.today().strftime('%d/%m/%Y')

    relatorio = relatorio_por_data.get(data)
    if not relatorio:
        await update.message.reply_text(f"Nenhum atendimento registrado para {data}.")
        return

    texto = f"\U0001F4C5 Relatório - {data}\n\n"
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
    print("🚀 Bot com persistência em JSON iniciado.")
    app.run_polling()
